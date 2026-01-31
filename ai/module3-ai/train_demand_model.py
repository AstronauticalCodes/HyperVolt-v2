
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, List, Dict
import json

from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau

class EnergyDemandForecaster:

    def __init__(self, lookback_hours: int = 24, forecast_horizon: int = 6):
        self.lookback_hours = lookback_hours
        self.forecast_horizon = forecast_horizon
        self.model = None
        self.scaler_X = MinMaxScaler()
        self.scaler_y = MinMaxScaler()
        self.feature_columns = None
        self.model_path = 'models/demand_forecaster.h5'
        self.scaler_path = 'models/demand_forecaster_scalers.pkl'
        self.config_path = 'models/demand_forecaster_config.json'

        os.makedirs('models', exist_ok=True)

    def prepare_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        self.feature_columns = [
            'total_energy_kwh',
            'temperature',
            'humidity',
            'solar_radiation_proxy',
            'carbon_intensity',
            'grid_price_per_kwh',
            'hour',
            'day_of_week',
            'is_weekend',
            'is_peak_hour',
            'occupancy_factor'
        ]

        available_features = [col for col in self.feature_columns if col in df.columns]
        if len(available_features) < len(self.feature_columns):
            print(f"Warning: Some features missing. Using {len(available_features)}/{len(self.feature_columns)}")
            self.feature_columns = available_features

        data = df[self.feature_columns].values

        data_scaled = self.scaler_X.fit_transform(data)

        X, y = [], []
        for i in range(self.lookback_hours, len(data_scaled) - self.forecast_horizon):
            X.append(data_scaled[i - self.lookback_hours:i])
            y.append(data[i:i + self.forecast_horizon, 0])

        X = np.array(X)
        y = np.array(y)

        y = self.scaler_y.fit_transform(y)

        print(f"Prepared data shape: X={X.shape}, y={y.shape}")
        return X, y

    def build_model(self, input_shape: Tuple) -> Sequential:
        model = Sequential([
            LSTM(128, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),

            LSTM(64, return_sequences=False),
            Dropout(0.2),

            Dense(32, activation='relu'),
            Dropout(0.1),

            Dense(self.forecast_horizon)
        ])

        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )

        return model

    def train(self, df: pd.DataFrame, epochs: int = 50, batch_size: int = 32,
              validation_split: float = 0.2) -> Dict:
        print("=" * 70)
        print("ENERGY DEMAND FORECASTING - MODEL TRAINING")
        print("=" * 70)

        print("\nPreparing training data...")
        X, y = self.prepare_data(df)

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, shuffle=False
        )

        print(f"Training set: {X_train.shape[0]} samples")
        print(f"Validation set: {X_val.shape[0]} samples")

        print("\nBuilding LSTM model...")
        self.model = self.build_model(input_shape=(X_train.shape[1], X_train.shape[2]))
        self.model.summary()

        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True,
                verbose=1
            ),
            ModelCheckpoint(
                self.model_path,
                monitor='val_loss',
                save_best_only=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=0.00001,
                verbose=1
            )
        ]

        print(f"\nTraining model for {epochs} epochs...")
        history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            verbose=1
        )

        print("\nEvaluating model...")
        val_predictions = self.model.predict(X_val)
        val_predictions = self.scaler_y.inverse_transform(val_predictions)
        y_val_actual = self.scaler_y.inverse_transform(y_val)

        mae = mean_absolute_error(y_val_actual.flatten(), val_predictions.flatten())
        mse = mean_squared_error(y_val_actual.flatten(), val_predictions.flatten())
        rmse = np.sqrt(mse)
        r2 = r2_score(y_val_actual.flatten(), val_predictions.flatten())

        metrics = {
            'mae': float(mae),
            'mse': float(mse),
            'rmse': float(rmse),
            'r2': float(r2),
            'training_samples': int(X_train.shape[0]),
            'validation_samples': int(X_val.shape[0])
        }

        print("\n" + "=" * 70)
        print("TRAINING RESULTS")
        print("=" * 70)
        print(f"Mean Absolute Error (MAE):  {mae:.4f} kWh")
        print(f"Root Mean Squared Error:    {rmse:.4f} kWh")
        print(f"R² Score:                   {r2:.4f}")
        print("=" * 70)

        self.save_model()

        return {
            'history': history.history,
            'metrics': metrics
        }

    def retrain(self, new_data_path: str, epochs: int = 20) -> Dict:
        print("=" * 70)
        print("MODEL RETRAINING ON NEW DATA")
        print("=" * 70)

        if not self.load_model():
            raise ValueError("No existing model found. Train a new model first.")

        print(f"\nLoading new data from: {new_data_path}")
        df_new = pd.read_csv(new_data_path)
        df_new['timestamp'] = pd.to_datetime(df_new['timestamp'])

        print(f"New data records: {len(df_new)}")

        X_new, y_new = self.prepare_data(df_new)

        print(f"\nRetraining model for {epochs} additional epochs...")
        history = self.model.fit(
            X_new, y_new,
            epochs=epochs,
            batch_size=32,
            validation_split=0.2,
            verbose=1
        )

        self.save_model()

        print("\n✓ Model retrained and saved successfully!")

        return {
            'history': history.history,
            'new_data_samples': int(X_new.shape[0])
        }

    def predict(self, recent_data: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained or loaded. Train or load model first.")

        data = recent_data[self.feature_columns].values
        data_scaled = self.scaler_X.transform(data)

        if len(data_scaled) < self.lookback_hours:
            raise ValueError(f"Need at least {self.lookback_hours} hours of recent data")

        X = data_scaled[-self.lookback_hours:].reshape(1, self.lookback_hours, -1)

        prediction_scaled = self.model.predict(X, verbose=0)
        prediction = self.scaler_y.inverse_transform(prediction_scaled)

        return prediction[0]

    def save_model(self):
        self.model.save(self.model_path)

        joblib.dump({
            'scaler_X': self.scaler_X,
            'scaler_y': self.scaler_y
        }, self.scaler_path)

        config = {
            'lookback_hours': self.lookback_hours,
            'forecast_horizon': self.forecast_horizon,
            'feature_columns': self.feature_columns,
            'trained_date': datetime.now().isoformat()
        }
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"\n✓ Model saved to: {self.model_path}")
        print(f"✓ Scalers saved to: {self.scaler_path}")
        print(f"✓ Config saved to: {self.config_path}")

    def load_model(self) -> bool:
        try:
            self.model = load_model(self.model_path)

            scalers = joblib.load(self.scaler_path)
            self.scaler_X = scalers['scaler_X']
            self.scaler_y = scalers['scaler_y']

            with open(self.config_path, 'r') as f:
                config = json.load(f)
            self.lookback_hours = config['lookback_hours']
            self.forecast_horizon = config['forecast_horizon']
            self.feature_columns = config['feature_columns']

            print(f"✓ Model loaded from: {self.model_path}")
            return True
        except Exception as e:
            print(f"✗ Failed to load model: {e}")
            return False

def main():
    data_path = 'data/raw/integrated_dataset.csv'

    if not os.path.exists(data_path):
        print(f"Error: Dataset not found at {data_path}")
        print("Please run 'python module3-ai/collect_all_data.py' first to generate datasets.")
        return

    print("Loading dataset...")
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print(f"Dataset loaded: {len(df)} records")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    forecaster = EnergyDemandForecaster(lookback_hours=24, forecast_horizon=6)

    results = forecaster.train(df, epochs=50, batch_size=32)

    print("\n" + "=" * 70)
    print("TESTING PREDICTION")
    print("=" * 70)
    recent_data = df.tail(24)
    prediction = forecaster.predict(recent_data)

    print("\nPredicted energy consumption for next 6 hours:")
    for i, pred in enumerate(prediction, 1):
        print(f"  Hour +{i}: {pred:.3f} kWh")

    print(f"\nTotal predicted: {prediction.sum():.2f} kWh (next 6 hours)")
    print(f"Average predicted: {prediction.mean():.3f} kWh/hour")

    print("\n" + "=" * 70)
    print("✓ MODEL TRAINING COMPLETE!")
    print("=" * 70)
    print("\nModel files saved in 'models/' directory:")
    print("  - demand_forecaster.h5 (trained model)")
    print("  - demand_forecaster_scalers.pkl (data scalers)")
    print("  - demand_forecaster_config.json (model configuration)")
    print("\nYou can now use this model for real-time energy demand forecasting!")

if __name__ == "__main__":
    main()
