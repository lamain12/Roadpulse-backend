# eta_trainer.py
import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from datetime import datetime
from haversine import haversine
from torch.utils.data import DataLoader, TensorDataset
import ast
import joblib
import os
import random
from zoneinfo import ZoneInfo

# =========================================
# Neural network model for ETA prediction
# =========================================
class ETA_Net(nn.Module):
    def __init__(self, input_dim):
        super(ETA_Net, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x):
        return self.net(x)

# =========================================
# Trainer class
# =========================================
class ETATrainer:
    def __init__(self, csv_file, finished_csv_file):
        here = os.path.dirname(__file__)
        scaler_X_path = os.path.join(here, "scaler_X.pkl")
        scaler_y_path = os.path.join(here, "scaler_y.pkl")
        model_path = os.path.join(here, "model.pth")
        self.csv_file = csv_file
        self.finished_csv_file = finished_csv_file
        self.model_path = model_path
        self.scaler_X_path = scaler_X_path
        self.scaler_y_path = scaler_y_path

        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()
        self.model = None

    # -------------------------------
    # Parse polyline string
    # -------------------------------
    def _parse_and_fix_polyline(self, polyline_str):
        try:
            coords = ast.literal_eval(polyline_str)
            if len(coords) < 2:
                return None
            return [(lat, lon) for lon, lat in coords]  # convert (lon,lat) -> (lat,lon)
        except:
            return None

    # -------------------------------
    # Calculate distance in km
    # -------------------------------
    def _calc_distance_km(self, coords):
        dist = 0
        for i in range(1, len(coords)):
            dist += haversine(coords[i-1], coords[i])
        return dist

    # -------------------------------
    # Load and preprocess dataset
    # -------------------------------
    def load_and_preprocess_data(self, nrows= 100000):
        datasets = []

        # ====== train.csv ======
        if self.csv_file and os.path.exists(self.csv_file):
            print(f"📂 Loading dataset: {self.csv_file}")
            df = pd.read_csv(self.csv_file, nrows=nrows)
            df = df[df["MISSING_DATA"] == False]
            df["coords"] = df["POLYLINE"].apply(self._parse_and_fix_polyline)
            df = df[df["coords"].notnull()]

            df["distance_km"] = df["coords"].apply(self._calc_distance_km)
            MYT = ZoneInfo("Asia/Kuala_Lumpur")
            df["departure_hour"] = df["TIMESTAMP"].apply(lambda ts: datetime.fromtimestamp(ts, tz=MYT).hour)
            df["day_of_week"] = df["TIMESTAMP"].apply(lambda ts: datetime.fromtimestamp(ts, tz=MYT).weekday())
            df["congestion_index"] = np.select(
            [
                (df["departure_hour"].between(6,9)) & (df["day_of_week"]<=4),
                (df["departure_hour"].between(6,9)) & (df["day_of_week"]>4),
                (df["departure_hour"].between(10,12)) & (df["day_of_week"]<=4),
                (df["departure_hour"].between(10,12)) & (df["day_of_week"]>4),
                (df["departure_hour"].between(13,16)) & (df["day_of_week"]<=4),
                (df["departure_hour"].between(13,16)) & (df["day_of_week"]>4),
                (df["departure_hour"].between(17,20))
            ],
            [1.6, 1.55, 1.25, 1.2, 1.2, 1.15, 1.7],
            default=1.0
            )
            # df["vehicle"] = "driving-car"
            # vehicle_weight = {"driving-car": 1.0, "cycling-regular": 1.3, "foot-walking": 3}
            # vehicle_mapping = {"driving-car":0, "cycling-regular":1, "foot-walking":2}
            # df["vehicle_code"] = df["vehicle"].map(vehicle_mapping)
            df["eta_minutes"] = (df["coords"].apply(len) - 1) * 15 / 60 * df["congestion_index"]
            df["temp"] = df["departure_hour"].apply(lambda h: 23 + 4.5*np.sin((h-6)/24*2*np.pi) + 4.5)
            df["rain"] = 0.0
            

            datasets.append(df[["distance_km","departure_hour","day_of_week","congestion_index","temp","rain",
                                # "vehicle_code", 
                                "eta_minutes"]])
            print (f"{len(df)} rows")

        # ====== finished_trips.csv ======
        if self.finished_csv_file and os.path.exists(self.finished_csv_file):
            print(f"📂 Loading finished trips: {self.finished_csv_file}")
            df2 = pd.read_csv(self.finished_csv_file)

            df2["eta_minutes"] = df2["real_eta"]

            datasets.append(df2[[
                "distance_km",
                "departure_hour",
                "day_of_week",
                "congestion_index",
                "temp",
                "rain",
                # "vehicle_code",
                "eta_minutes"
            ]])
            print (f"{len(df2)} rows")

        if not datasets:
             raise FileNotFoundError("No valid CSV files found.")

        df_all = pd.concat(datasets, ignore_index=True)
        print(f"✅ Combined dataset size: {len(df_all)} rows")

        features = ["distance_km","departure_hour","day_of_week","congestion_index","temp","rain", 
                    # "vehicle_code"
                    ]
        X = df_all[features].values
        y = np.log1p(df_all["eta_minutes"].values).reshape(-1,1)

        print("📊 Scaling features and labels...")
        X = self.scaler_X.fit_transform(X)
        y = self.scaler_y.fit_transform(y)
        joblib.dump(self.scaler_X, self.scaler_X_path)
        joblib.dump(self.scaler_y, self.scaler_y_path)

        print("✅ Data preprocessing complete.")
        return train_test_split(X, y, test_size=0.2, random_state=42)

    # -------------------------------
    # Train model
    # -------------------------------
    def train(self, epochs=500, patience=50, batch_size=64, lr=0.001, seed=999):
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False

        X_train, X_val, y_train, y_val = self.load_and_preprocess_data()
        X_train_tensor = torch.tensor(X_train,dtype=torch.float32)
        y_train_tensor = torch.tensor(y_train,dtype=torch.float32)
        X_val_tensor = torch.tensor(X_val,dtype=torch.float32)
        y_val_tensor = torch.tensor(y_val,dtype=torch.float32)
        train_dataset = TensorDataset(X_train_tensor,y_train_tensor)
        train_loader = DataLoader(train_dataset,batch_size=batch_size,shuffle=True)

        self.model = ETA_Net(X_train.shape[1])
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)

        best_val_loss = float("inf")
        patience_counter = 0

        print(f"🚀 Starting training...")
        for epoch in range(epochs):
            self.model.train()
            for xb, yb in train_loader:
                optimizer.zero_grad()
                loss = criterion(self.model(xb), yb)
                loss.backward()
                optimizer.step()

            self.model.eval()
            with torch.no_grad():
                val_loss = criterion(self.model(X_val_tensor), y_val_tensor).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_model_state = self.model.state_dict()
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"⏹ Early stopping at epoch {epoch}")
                    break

            if epoch % 10 == 0:
                print(f"Epoch {epoch:03d} | Val Loss: {val_loss:.4f}")

        self.model.load_state_dict(best_model_state)
        torch.save(self.model.state_dict(), self.model_path)
        print(f"✅ Model saved to {self.model_path}")

    # -------------------------------
    # Load model
    # -------------------------------
    def load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"{self.model_path} not found.")
        print("📦 Loading scalers and model...")
        self.scaler_X = joblib.load(self.scaler_X_path)
        self.scaler_y = joblib.load(self.scaler_y_path)
        self.model = ETA_Net(input_dim=6)
        self.model.load_state_dict(torch.load(self.model_path))
        self.model.eval()
        print("✅ Model loaded and ready.")

# -------------------------------
# CLI
# -------------------------------
if __name__ == "__main__":
    here = os.path.dirname(__file__)
    trainer = ETATrainer(os.path.join(here, "train.csv"), os.path.join(here, "finished_trips.csv"))
    trainer.train()
    trainer.load_model()
