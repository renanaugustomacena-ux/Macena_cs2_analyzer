import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.win_probability")

WIN_PROB_EPOCHS = 100
WIN_PROB_MIN_SAMPLES = 20  # AR-6: Minimum samples for meaningful train/val split
WIN_PROB_TRAINER_INPUT_DIM = 9


class WinProbabilityTrainerNN(nn.Module):
    """Lightweight win probability model for offline training on pro match DataFrames.

    Uses 9 raw game-state features (alive, health, armor, equipment, bomb).
    NOTE: This is separate from the real-time predictor WinProbabilityNN in
    backend/analysis/win_probability.py (12 normalized features, 64/32 hidden dims).
    Do NOT cross-load checkpoints between them.
    """

    def __init__(self, input_dim=WIN_PROB_TRAINER_INPUT_DIM):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        return self.model(x)


# A-12: Backward-compatibility alias REMOVED. The name WinProbabilityNN is
# defined in backend/analysis/win_probability.py (12-dim, 64/32 hidden).
# Import WinProbabilityTrainerNN explicitly for the 9-dim offline trainer.


def train_win_prob_model(data_df: pd.DataFrame, model_path: str):
    """
    Trains the Win Probability model using match snapshots.
    P1-10: Adds train/val split, early stopping, and reproducibility.
    """
    from Programma_CS2_RENAN.backend.nn.config import set_global_seed
    from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping

    set_global_seed()  # P1-02: Reproducible training

    features = [
        "ct_alive",
        "t_alive",
        "ct_health",
        "t_health",
        "ct_armor",
        "t_armor",
        "ct_eqp",
        "t_eqp",
        "bomb_planted",
    ]
    X_all = torch.tensor(data_df[features].values, dtype=torch.float32)
    y_all = torch.tensor(data_df["did_ct_win"].values, dtype=torch.float32).reshape(-1, 1)

    # P1-04 / AR-6: Refuse to train with insufficient data
    if len(X_all) < WIN_PROB_MIN_SAMPLES:
        logger.warning(
            "Insufficient training data (%d < %d). Skipping win probability training.",
            len(X_all), WIN_PROB_MIN_SAMPLES,
        )
        return None

    # P1-10: Train/val split (80/20)
    X_train, X_val, y_train, y_val = train_test_split(
        X_all.numpy(), y_all.numpy(), test_size=0.2, random_state=42
    )
    X_train = torch.tensor(X_train, dtype=torch.float32)
    X_val = torch.tensor(X_val, dtype=torch.float32)
    y_train = torch.tensor(y_train, dtype=torch.float32)
    y_val = torch.tensor(y_val, dtype=torch.float32)

    model = WinProbabilityTrainerNN(input_dim=len(features))
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    early_stopper = EarlyStopping(patience=10, min_delta=1e-4)  # P1-01

    for epoch in range(WIN_PROB_EPOCHS):
        # Training
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        loss.backward()
        optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_loss = criterion(val_outputs, y_val).item()

        if epoch % 20 == 0:
            logger.info("Epoch %s, Train Loss: %s, Val Loss: %s", epoch, format(loss.item(), ".4f"), format(val_loss, ".4f"))

        # P1-01: Early stopping based on validation loss
        if early_stopper(val_loss):
            logger.info("Win probability early stopping at epoch %d", epoch)
            break

    torch.save(model.state_dict(), model_path)
    return model


def predict_win_prob(model, state_dict: dict):
    """
    Predicts win probability for a given state.
    """
    features = [
        "ct_alive",
        "t_alive",
        "ct_health",
        "t_health",
        "ct_armor",
        "t_armor",
        "ct_eqp",
        "t_eqp",
        "bomb_planted",
    ]
    x = torch.tensor([[state_dict.get(f, 0) for f in features]], dtype=torch.float32)
    model.eval()
    with torch.no_grad():
        prob = model(x).item()
    return prob
