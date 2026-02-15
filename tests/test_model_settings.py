from configs.base import load_model_settings


class TestLoadModelSettings:
    def test_reads_models_key(self) -> None:
        config = {
            "models": {
                "random_forest": {
                    "enabled": True,
                    "n_estimators": 123,
                    "max_depth": 7,
                    "min_samples_split": 4,
                    "random_state": 99,
                    "n_jobs": 2,
                    "verbose": 1,
                },
                "xgboost": {
                    "enabled": False,
                    "n_estimators": 222,
                    "max_depth": 8,
                    "learning_rate": 0.12,
                    "subsample": 0.8,
                    "colsample_bytree": 0.7,
                    "min_child_weight": 2.5,
                    "gamma": 0.2,
                    "reg_alpha": 0.15,
                    "reg_lambda": 1.2,
                    "random_state": 7,
                    "n_jobs": 3,
                    "verbosity": 1,
                },
                "prophet": {
                    "enabled": True,
                    "seasonality_mode": "multiplicative",
                    "changepoint_prior_scale": 0.1,
                    "seasonality_prior_scale": 5.0,
                    "yearly_seasonality": True,
                    "weekly_seasonality": False,
                    "daily_seasonality": True,
                },
            }
        }

        settings = load_model_settings(config)

        assert settings.random_forest.enabled is True
        assert settings.random_forest.n_estimators == 123
        assert settings.random_forest.max_depth == 7
        assert settings.random_forest.min_samples_split == 4
        assert settings.random_forest.random_state == 99
        assert settings.random_forest.n_jobs == 2
        assert settings.random_forest.verbose == 1
        assert settings.xgboost.enabled is False
        assert settings.xgboost.n_estimators == 222
        assert settings.xgboost.max_depth == 8
        assert settings.xgboost.learning_rate == 0.12
        assert settings.xgboost.subsample == 0.8
        assert settings.xgboost.colsample_bytree == 0.7
        assert settings.xgboost.min_child_weight == 2.5
        assert settings.xgboost.gamma == 0.2
        assert settings.xgboost.reg_alpha == 0.15
        assert settings.xgboost.reg_lambda == 1.2
        assert settings.xgboost.random_state == 7
        assert settings.xgboost.n_jobs == 3
        assert settings.xgboost.verbosity == 1
        assert settings.prophet.enabled is True
        assert settings.prophet.seasonality_mode == "multiplicative"
        assert settings.prophet.changepoint_prior_scale == 0.1
        assert settings.prophet.seasonality_prior_scale == 5.0
        assert settings.prophet.yearly_seasonality is True
        assert settings.prophet.weekly_seasonality is False
        assert settings.prophet.daily_seasonality is True

    def test_reads_legacy_model_key(self) -> None:
        config = {"model": {"random_forest": {"verbose": 2}}}

        settings = load_model_settings(config)

        assert settings.random_forest.enabled is False
        assert settings.random_forest.verbose == 2
        assert settings.xgboost.enabled is False
        assert settings.prophet.enabled is False

    def test_enabled_defaults_to_false_when_missing(self) -> None:
        config = {
            "models": {
                "random_forest": {"n_estimators": 10},
                "xgboost": {"n_estimators": 20},
                "prophet": {"seasonality_mode": "additive"},
            }
        }

        settings = load_model_settings(config)

        assert settings.random_forest.enabled is False
        assert settings.xgboost.enabled is False
        assert settings.prophet.enabled is False
