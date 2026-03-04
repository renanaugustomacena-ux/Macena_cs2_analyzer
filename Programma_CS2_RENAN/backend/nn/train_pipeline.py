import torch
import torch.nn as nn
from sqlmodel import select
from torch.utils.data import DataLoader

from Programma_CS2_RENAN.backend.nn.config import BATCH_SIZE, EPOCHS, HIDDEN_DIM, INPUT_DIM, LEARNING_RATE, OUTPUT_DIM
from Programma_CS2_RENAN.backend.nn.dataset import ProPerformanceDataset
from Programma_CS2_RENAN.backend.nn.model import TeacherRefinementNN
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn_train")


def run_training():
    db_manager = get_db_manager()
    X, y = _prepare_training_data(db_manager)

    if not X:
        return

    dataset = ProPerformanceDataset(X, y)
    loader = DataLoader(dataset, batch_size=min(BATCH_SIZE, len(dataset)), shuffle=True)

    model = TeacherRefinementNN(INPUT_DIM, OUTPUT_DIM, HIDDEN_DIM)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-2)
    loss_fn = nn.MSELoss()

    logger.info("Starting training on %s samples...", len(X))
    _execute_training_loop(model, loader, optimizer, loss_fn)
    _finalize_training(model)


def _prepare_training_data(db_manager):
    X, y = [], []
    with db_manager.get_session() as session:
        results = session.exec(select(PlayerMatchStats)).all()
        if len(results) < 5:
            logger.warning("Not enough data to train. Found %s.", len(results))
            return None, None
        for r in results:
            X.append(_extract_features(r))
            # Training labels: per-feature deviation from pro baseline (rating=1.05)
            # Provides gradient signal proportional to distance from pro mean
            rating_delta = r.rating - 1.05 if r.rating else -0.1
            adr_delta = (r.avg_adr - 80.0) / 80.0 if r.avg_adr else 0.0
            kd_delta = (r.kd_ratio - 1.0) if r.kd_ratio else 0.0
            hs_delta = (r.avg_hs - 0.50) if r.avg_hs else 0.0
            y.append([rating_delta, adr_delta, kd_delta, hs_delta])
    return X, y


def _extract_features(r):
    # Match-aggregate features from PlayerMatchStats (12 values)
    # Padded to INPUT_DIM for model compatibility.
    # The canonical tick-level pipeline (TrainingOrchestrator) uses full 19-dim vectors.
    base = [
        r.avg_kills,
        r.avg_deaths,
        r.avg_adr,
        r.avg_hs,
        r.avg_kast,
        r.kill_std,
        r.adr_std,
        r.kd_ratio,
        r.impact_rounds,
        r.anomaly_score,
        r.accuracy,
        r.econ_rating,
    ]
    # Pad remaining dimensions with 0.0 to match INPUT_DIM
    return base + [0.0] * (INPUT_DIM - len(base))


def _execute_training_loop(model, loader, optimizer, loss_fn):
    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        _log_epoch(epoch, total_loss)


def _log_epoch(epoch, total_loss):
    if (epoch + 1) % 10 == 0:
        logger.info("Epoch %s: loss=%s", epoch + 1, format(total_loss, ".4f"))


def _finalize_training(model):
    from Programma_CS2_RENAN.backend.nn.persistence import save_nn

    save_nn(model, "latest")
    logger.info("Training complete. Model saved as 'latest'.")


if __name__ == "__main__":
    run_training()
