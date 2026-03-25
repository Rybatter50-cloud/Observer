#!/usr/bin/env python3
"""
Observer Lite - Classifier Training Script
===========================================
Train a multi-label sentence-transformer classifier on risk-indicator-labeled articles.

Usage:
    python scripts/train_classifier.py
    python scripts/train_classifier.py --backfill
    python scripts/train_classifier.py --backfill --min-confidence 0.3

What it does:
    1. Connects to the Observer PostgreSQL database
    2. Fetches all processed signals with risk indicators (analyst-scored articles)
    3. Encodes titles using sentence-transformers (all-MiniLM-L6-v2)
    4. Trains a OneVsRestClassifier(LogisticRegression) for multi-label
    5. Evaluates with cross-validation (F1 micro/samples)
    6. Saves classifier + MultiLabelBinarizer to models/classifier.pkl
    7. Optionally classifies unlabeled articles and updates the DB (--backfill)

Requirements:
    pip install sentence-transformers scikit-learn joblib asyncpg

2026-03-25 | Ported from RYBAT for Observer Lite
"""

import os
import sys
import time
import asyncio
import argparse
import numpy as np
from pathlib import Path
from collections import Counter

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


async def fetch_training_data(min_samples: int = 20):
    """Fetch labeled articles from the database."""
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / '.env')

    import asyncpg
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    print("\nConnecting to database...")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)

    try:
        # Labeled articles (has risk indicators, processed = TRUE)
        labeled_rows = await pool.fetch("""
            SELECT title, risk_indicators, relevance_score
            FROM intel_signals
            WHERE processed = TRUE
              AND cardinality(risk_indicators) > 0
              AND title IS NOT NULL
              AND LENGTH(title) > 10
            ORDER BY created_at DESC
        """)

        # Unlabeled articles (no indicators assigned)
        unlabeled_rows = await pool.fetch("""
            SELECT id, title, relevance_score
            FROM intel_signals
            WHERE processed = TRUE
              AND (risk_indicators = '{}' OR risk_indicators IS NULL)
              AND title IS NOT NULL
              AND LENGTH(title) > 10
            ORDER BY created_at DESC
        """)

        print(f"  Labeled articles:    {len(labeled_rows)}")
        print(f"  Unlabeled articles:  {len(unlabeled_rows)}")

        # Check indicator distribution
        indicator_counts = Counter()
        for r in labeled_rows:
            for ind in (r['risk_indicators'] or []):
                indicator_counts[ind] += 1
        print(f"\n  Indicator distribution:")
        for ind, count in indicator_counts.most_common():
            print(f"    {ind:5s} {count:5d}")

        # Filter: keep rows where at least one indicator has enough samples
        valid_indicators = {ind for ind, count in indicator_counts.items() if count >= min_samples}
        filtered_rows = [r for r in labeled_rows if any(i in valid_indicators for i in (r['risk_indicators'] or []))]
        dropped = len(labeled_rows) - len(filtered_rows)
        if dropped > 0:
            print(f"\n  Dropped {dropped} samples from indicators with < {min_samples} examples")

        return filtered_rows, unlabeled_rows

    finally:
        await pool.close()


def train_classifier(titles, indicator_lists, model_name='all-MiniLM-L6-v2', output_path=None):
    """Encode titles and train a multi-label OneVsRest(LogisticRegression) classifier."""
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer
    from sklearn.model_selection import KFold
    from sklearn.metrics import f1_score, classification_report
    import joblib

    if output_path is None:
        output_path = str(_PROJECT_ROOT / 'models' / 'classifier.pkl')

    # Encode
    print(f"\nLoading model: {model_name}")
    model = SentenceTransformer(model_name)

    print(f"Encoding {len(titles)} titles...")
    start = time.time()
    embeddings = model.encode(titles, show_progress_bar=True, batch_size=64, convert_to_numpy=True)
    encode_time = time.time() - start
    print(f"  Encoded in {encode_time:.1f}s ({len(titles)/encode_time:.0f} titles/sec)")
    print(f"  Embedding shape: {embeddings.shape}")

    # Multi-label binarize
    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(indicator_lists)
    print(f"  Indicator classes: {list(mlb.classes_)}")
    print(f"  Label matrix shape: {Y.shape}")

    # Cross-validate
    print(f"\nCross-validation (5-fold):")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    clf = OneVsRestClassifier(LogisticRegression(max_iter=1000, C=1.0, solver='lbfgs'))

    f1_micro_scores = []
    f1_samples_scores = []
    for fold, (train_idx, val_idx) in enumerate(kf.split(embeddings)):
        X_train, X_val = embeddings[train_idx], embeddings[val_idx]
        Y_train, Y_val = Y[train_idx], Y[val_idx]
        clf.fit(X_train, Y_train)
        Y_pred = clf.predict(X_val)
        f1_micro_scores.append(f1_score(Y_val, Y_pred, average='micro', zero_division=0))
        f1_samples_scores.append(f1_score(Y_val, Y_pred, average='samples', zero_division=0))

    f1_micro_scores = np.array(f1_micro_scores)
    f1_samples_scores = np.array(f1_samples_scores)
    print(f"  F1 micro:   {f1_micro_scores.mean():.3f} (+/- {f1_micro_scores.std():.3f})")
    print(f"  F1 samples: {f1_samples_scores.mean():.3f} (+/- {f1_samples_scores.std():.3f})")
    print(f"  Per-fold micro: {', '.join(f'{s:.3f}' for s in f1_micro_scores)}")

    # Full classification report
    from sklearn.model_selection import cross_val_predict
    Y_pred_all = cross_val_predict(clf, embeddings, Y, cv=kf)
    print(f"\n  Classification Report (cross-validated):")
    print(classification_report(Y, Y_pred_all, target_names=mlb.classes_, digits=3, zero_division=0))

    # Train final model on all data
    print("Training final model on all data...")
    clf.fit(embeddings, Y)

    # Save
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        'classifier': clf,
        'multi_label_binarizer': mlb,
        'model_name': model_name,
        'n_samples': len(titles),
        'n_classes': len(mlb.classes_),
        'classes': list(mlb.classes_),
        'cv_f1_micro': float(f1_micro_scores.mean()),
        'cv_f1_std': float(f1_micro_scores.std()),
    }, output)
    print(f"\nSaved classifier to {output} ({output.stat().st_size / 1024:.1f} KB)")

    return model, clf, mlb, embeddings


def preview_unlabeled(model, clf, mlb, unlabeled_rows, limit=20):
    """Show predictions for a sample of unlabeled articles."""
    if not unlabeled_rows:
        print("\nNo unlabeled articles to preview.")
        return

    titles = [r['title'] for r in unlabeled_rows[:limit]]
    embeddings = model.encode(titles, convert_to_numpy=True, show_progress_bar=False)
    predictions = clf.predict(embeddings)
    predicted_labels = mlb.inverse_transform(predictions)
    probas = np.array([est.predict_proba(embeddings)[:, 1] for est in clf.estimators_]).T

    print(f"\n{'='*80}")
    print(f"PREVIEW: Predictions for {min(limit, len(unlabeled_rows))} unlabeled articles")
    print(f"{'='*80}")
    for i, title in enumerate(titles):
        indicators = list(predicted_labels[i]) if predicted_labels[i] else []
        top_conf = max(probas[i]) if len(probas[i]) > 0 else 0
        ind_str = ','.join(indicators) if indicators else '(none)'
        print(f"  [{top_conf:.2f}] {ind_str:12s}  {title[:70]}")


async def backfill_classifications(model, clf, mlb, min_confidence: float = 0.3):
    """Classify all unlabeled articles and write back to DB."""
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / '.env')

    import asyncpg
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print("ERROR: DATABASE_URL not set.")
        return

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)

    try:
        rows = await pool.fetch("""
            SELECT id, title
            FROM intel_signals
            WHERE (risk_indicators = '{}' OR risk_indicators IS NULL)
              AND title IS NOT NULL
              AND LENGTH(title) > 10
            ORDER BY id
        """)

        if not rows:
            print("\nNo articles to backfill.")
            return

        print(f"\n{'='*60}")
        print(f"BACKFILL: Classifying {len(rows)} articles")
        print(f"  Minimum confidence: {min_confidence}")
        print(f"{'='*60}")

        titles = [r['title'] for r in rows]
        print(f"  Encoding {len(titles)} titles...")
        embeddings = model.encode(titles, convert_to_numpy=True, show_progress_bar=True, batch_size=64)

        predictions = clf.predict(embeddings)
        predicted_labels = mlb.inverse_transform(predictions)
        probas = np.array([est.predict_proba(embeddings)[:, 1] for est in clf.estimators_]).T

        updated = 0
        skipped = 0
        indicator_counts = Counter()

        for i, row in enumerate(rows):
            indicators = list(predicted_labels[i]) if predicted_labels[i] else []

            if indicators and len(probas[i]) > 0:
                matched_mask = np.array([cls in indicators for cls in mlb.classes_])
                confidence = float(np.mean(probas[i][matched_mask]))
            else:
                confidence = float(max(probas[i])) if len(probas[i]) > 0 else 0

            if confidence < min_confidence or not indicators:
                skipped += 1
                continue

            for ind in indicators:
                indicator_counts[ind] += 1

            base = (confidence - 0.5) * 200
            bonus = min(20, (len(indicators) - 1) * 10)
            relevance_score = int(max(10, min(95, base + bonus)))

            await pool.execute("""
                UPDATE intel_signals
                SET risk_indicators = $1::TEXT[],
                    relevance_score = $3,
                    analysis_mode = 'LOCAL',
                    processed = TRUE
                WHERE id = $2
            """, indicators, row['id'], relevance_score)
            updated += 1

        print(f"\n  Results:")
        print(f"    Updated:  {updated}")
        print(f"    Skipped:  {skipped} (confidence < {min_confidence} or no indicators)")
        print(f"\n  Indicator breakdown:")
        for ind, count in indicator_counts.most_common():
            print(f"    {ind:15s} {count:5d}")

    finally:
        await pool.close()


async def main():
    parser = argparse.ArgumentParser(description='Train Observer article classifier')
    parser.add_argument(
        '--model', default='all-MiniLM-L6-v2',
        help='Sentence-transformer model name (default: all-MiniLM-L6-v2)',
    )
    parser.add_argument('--output', default=None, help='Output path for classifier pkl')
    parser.add_argument('--min-samples', type=int, default=20, help='Minimum samples per class')
    parser.add_argument('--preview', type=int, default=20, help='Number of unlabeled articles to preview')
    parser.add_argument('--backfill', action='store_true', help='Classify unlabeled articles and update DB')
    parser.add_argument('--min-confidence', type=float, default=0.5, help='Minimum confidence for backfill')
    args = parser.parse_args()

    print("=" * 60)
    print("Observer Classifier Training")
    print("=" * 60)

    labeled, unlabeled = await fetch_training_data(args.min_samples)

    if len(labeled) < 50:
        print(f"\nERROR: Only {len(labeled)} labeled articles. Need at least 50 for training.")
        print("Score more articles via the dashboard to build up training data.")
        sys.exit(1)

    titles = [r['title'] for r in labeled]
    indicator_lists = [list(r['risk_indicators'] or []) for r in labeled]

    model, clf, mlb, embeddings = train_classifier(
        titles, indicator_lists,
        model_name=args.model,
        output_path=args.output,
    )

    if args.preview > 0:
        preview_unlabeled(model, clf, mlb, unlabeled, limit=args.preview)

    if args.backfill:
        await backfill_classifications(model, clf, mlb, min_confidence=args.min_confidence)

    print(f"\n{'='*60}")
    print(f"DONE. Classifier ready for {len(mlb.classes_)} indicator classes.")
    print(f"  Model: {args.model}")
    print(f"  Trained on: {len(labeled)} articles")
    if not args.backfill and unlabeled:
        print(f"  Can classify: {len(unlabeled)} unlabeled articles")
        print(f"  Run with --backfill to classify them now")
    print(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())
