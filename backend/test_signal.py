import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prediction.trading.signal_generator import generate_trade_signal

features = {'realized_vol_20d': 27.062, 'vix': 20.0, 'news_sentiment': -0.20} # Assuming extreme news sentiment based on previous check
pred_result = {'ensemble_prob': 0.5, 'confidence': 0.0, 'expected_return': 0.75, 'horizon_days': 5}
regime_state = {'regime_label': 'NEUTRAL', 'severity': 0.0, 'regime_age_days': 15, 'is_transition': False}

signal = generate_trade_signal(
    symbol='WTI',
    forecast=pred_result,
    regime_state=regime_state,
    current_price=80.1,
    features=features,
    is_intraday=True
)
print('Target Price:', signal.get('target_price'))
print('Entry Low:', signal.get('entry_low'))
print('Entry High:', signal.get('entry_high'))
print('Stop Loss:', signal.get('stop_loss'))
