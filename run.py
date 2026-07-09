"""
AKI Prediction Project - Main Entry Point
One-click run for the entire pipeline.
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.helpers import logger, setup_logging


def run_data_pipeline(input_path=None, output_dir=None):
    """Run data cleaning and EDA pipeline."""
    logger.info("=" * 60)
    logger.info("Phase 1: Data Cleaning & EDA")
    logger.info("=" * 60)

    from src.data.cleaning import run_full_cleaning_pipeline
    from src.data.eda import run_full_eda

    if input_path is None:
        input_path = PROJECT_ROOT / 'data' / 'raw' / 'AKI数据.xlsx'

    # 1. Data cleaning
    processed_path = PROJECT_ROOT / 'data' / 'processed' / 'cleaned_data.csv'
    run_full_cleaning_pipeline(str(input_path), str(PROJECT_ROOT / 'data' / 'processed'))

    # 2. EDA
    eda_results = run_full_eda(str(processed_path), str(PROJECT_ROOT / 'outputs'))

    logger.info("Phase 1 complete!")
    return processed_path


def run_modeling_pipeline(data_path=None, use_smote=True, cv=5):
    """Run feature engineering, model training, and evaluation."""
    logger.info("=" * 60)
    logger.info("Phase 2: Feature Engineering & Model Training")
    logger.info("=" * 60)

    import pandas as pd
    from src.data.features import run_full_feature_engineering
    from src.models.train import run_full_model_training
    from src.models.evaluate import run_full_evaluation

    if data_path is None:
        data_path = PROJECT_ROOT / 'data' / 'processed' / 'cleaned_data.csv'

    df = pd.read_csv(data_path)

    # 3. Feature engineering
    categorical_cols = ['手术类型'] if '手术类型' in df.columns else []
    clinical_features = ['年龄', '术前Scr', '术前eGFR', 'APACHEII', '手术时间',
                          '术中尿量', '术中失血量', '高血压', '糖尿病']

    X, y, selected_features, encoders, scaler = run_full_feature_engineering(
        df, target='AKI分组',
        categorical_cols=categorical_cols,
        clinical_features=clinical_features,
        imbalance_method='smote' if use_smote else None
    )

    # 4. Model training
    model_results = run_full_model_training(
        X.values, y.values,
        output_dir=str(PROJECT_ROOT / 'models'),
        cv=cv,
        use_smote=use_smote
    )

    # 5. Model evaluation
    eval_summary = run_full_evaluation(
        model_results['models'],
        model_results['X_test'],
        model_results['y_test'],
        output_dir=str(PROJECT_ROOT / 'outputs')
    )

    logger.info("Phase 2 complete!")
    return model_results, eval_summary


def run_shap_pipeline(model_results, X, feature_names):
    """Run SHAP analysis."""
    logger.info("=" * 60)
    logger.info("Phase 3: SHAP Analysis")
    logger.info("=" * 60)

    from src.visualization.shap_viz import run_full_shap_analysis

    # Get best model (first one = highest AUC)
    best_name = list(model_results.keys())[0]
    best_model = model_results[best_name]

    shap_results = run_full_shap_analysis(
        best_model, X, feature_names=feature_names,
        model_type='tree', top_n=15
    )

    logger.info("Phase 3 complete!")
    return shap_results


def run_calibration_pipeline(model_results_dict):
    """Run calibration and DCA analysis."""
    logger.info("=" * 60)
    logger.info("Phase 3b: Calibration & DCA Analysis")
    logger.info("=" * 60)

    from src.models.calibration import run_full_calibration_analysis

    cal_results = run_full_calibration_analysis(model_results_dict)

    logger.info("Calibration analysis complete!")
    return cal_results


def run_web_app():
    """Launch Streamlit web application."""
    import subprocess
    web_path = PROJECT_ROOT / 'web' / 'app.py'
    subprocess.run(['streamlit', 'run', str(web_path)])


def main():
    parser = argparse.ArgumentParser(
        description='AKI Prediction Project - Complete Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --all              # Run complete pipeline
  python run.py --data             # Run data cleaning + EDA only
  python run.py --model            # Run modeling only
  python run.py --web              # Launch web application
  python run.py --data --model     # Run data + modeling
        """
    )

    parser.add_argument('--all', action='store_true', help='Run complete pipeline')
    parser.add_argument('--data', action='store_true', help='Run data processing pipeline')
    parser.add_argument('--model', action='store_true', help='Run modeling pipeline')
    parser.add_argument('--shap', action='store_true', help='Run SHAP analysis')
    parser.add_argument('--web', action='store_true', help='Launch Streamlit web app')
    parser.add_argument('--input', type=str, help='Path to raw data file')
    parser.add_argument('--no-smote', action='store_true', help='Disable SMOTE resampling')
    parser.add_argument('--cv', type=int, default=5, help='Cross-validation folds')
    parser.add_argument('--test-size', type=float, default=0.2, help='Test set proportion')

    args = parser.parse_args()

    setup_logging(level='INFO')

    # Default to --all if no args
    if not any([args.all, args.data, args.model, args.shap, args.web]):
        args.all = True

    try:
        processed_path = None
        model_results = None

        # Data pipeline
        if args.all or args.data:
            processed_path = run_data_pipeline(args.input)

        # Modeling pipeline
        if args.all or args.model:
            model_results, eval_summary = run_modeling_pipeline(
                processed_path,
                use_smote=not args.no_smote,
                cv=args.cv
            )

        # SHAP analysis
        if args.all or args.shap:
            if model_results is None:
                logger.error("Model results required for SHAP. Run --model first.")
                return

            import pandas as pd
            if processed_path:
                df = pd.read_csv(processed_path)
            else:
                df = pd.read_csv(PROJECT_ROOT / 'data' / 'processed' / 'cleaned_data.csv')

            # Get feature names from feature selection
            from src.data.features import run_full_feature_engineering
            X, y, feature_names, _, _ = run_full_feature_engineering(
                df, target='AKI分组',
                categorical_cols=['手术类型'] if '手术类型' in df.columns else [],
                imbalance_method=None  # Don't resample for SHAP
            )

            run_shap_pipeline(model_results['models'], X, feature_names)

            # Calibration
            model_probs_dict = {}
            for name, model in model_results['models'].items():
                if hasattr(model, 'predict_proba'):
                    model_probs_dict[name] = {
                        'y_true': model_results['y_test'],
                        'y_prob': model.predict_proba(model_results['X_test'])[:, 1]
                    }
            if model_probs_dict:
                run_calibration_pipeline(model_probs_dict)

        # Web app
        if args.all or args.web:
            logger.info("Launching Streamlit web application...")
            run_web_app()

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
