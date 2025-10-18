"""
Analysis script for Solar Mining data
Reads CSV and displays statistics + creates simple plots
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_FILE = Path("logs/solar_data.csv")

def load_data():
    """Load CSV data."""
    if not DATA_FILE.exists():
        print(f"❌ No data found: {DATA_FILE}")
        return None
    
    df = pd.read_csv(DATA_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def show_statistics(df):
    """Display basic statistics."""
    print("=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Time period: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Data points: {len(df)}")
    print()
    
    print("SOLAR PRODUCTION:")
    print(f"  Average: {df['solar_production_w'].mean():.0f} W")
    print(f"  Maximum: {df['solar_production_w'].max():.0f} W")
    print(f"  Minimum: {df['solar_production_w'].min():.0f} W")
    print()
    
    print("HOUSE CONSUMPTION:")
    print(f"  Average: {df['house_consumption_w'].mean():.0f} W")
    print(f"  Maximum: {df['house_consumption_w'].max():.0f} W")
    print(f"  Minimum: {df['house_consumption_w'].min():.0f} W")
    print()
    
    print("GRID FEED-IN:")
    print(f"  Average: {df['grid_feed_in_w'].mean():.0f} W")
    print(f"  Maximum: {df['grid_feed_in_w'].max():.0f} W")
    print(f"  Total: {df['grid_feed_in_w'].sum() * 30 / 3600:.2f} kWh (at 30s interval)")
    print()
    
    print("MINING:")
    mining_time = df['mining_active'].sum() * 30 / 3600  # 30s interval
    total_time = len(df) * 30 / 3600
    print(f"  Mining time: {mining_time:.2f} h ({mining_time/total_time*100:.1f}%)")
    print(f"  Average hashrate: {df[df['hashrate_mhs']>0]['hashrate_mhs'].mean():.2f} MH/s")
    print(f"  GPU temperature (mining): {df[df['mining_active']==1]['gpu_temp_c'].mean():.1f}°C")
    print()
    
    if df['mining_paused'].sum() > 0:
        pause_time = df['mining_paused'].sum() * 30 / 60
        print(f"GPU PAUSES:")
        print(f"  Paused: {pause_time:.1f} minutes")
        print()

def plot_overview(df):
    """Create overview plot."""
    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    
    # Solar production & consumption
    axes[0].plot(df['timestamp'], df['solar_production_w'], label='Solar Production', color='orange')
    axes[0].plot(df['timestamp'], df['house_consumption_w'], label='House Consumption', color='blue')
    axes[0].plot(df['timestamp'], df['grid_feed_in_w'], label='Grid Feed-in', color='green')
    axes[0].set_ylabel('Power (W)')
    axes[0].legend(loc='upper left')
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title('Solar & Consumption')
    
    # Available power
    axes[1].plot(df['timestamp'], df['available_for_mining_w'], label='Available for Mining', color='purple')
    axes[1].axhline(y=200, color='g', linestyle='--', label='Start Threshold (200W)')
    axes[1].axhline(y=150, color='r', linestyle='--', label='Stop Threshold (150W)')
    axes[1].set_ylabel('Power (W)')
    axes[1].legend(loc='upper left')
    axes[1].grid(True, alpha=0.3)
    axes[1].set_title('Available Power')
    
    # Mining status & hashrate
    axes[2].fill_between(df['timestamp'], 0, df['mining_active']*30, 
                          label='Mining Active', alpha=0.3, color='green')
    axes[2].set_ylabel('Mining Status')
    axes[2].set_ylim(-1, 35)
    ax2_right = axes[2].twinx()
    ax2_right.plot(df['timestamp'], df['hashrate_mhs'], label='Hashrate', color='red', linewidth=2)
    ax2_right.set_ylabel('Hashrate (MH/s)', color='red')
    ax2_right.tick_params(axis='y', labelcolor='red')
    axes[2].legend(loc='upper left')
    ax2_right.legend(loc='upper right')
    axes[2].grid(True, alpha=0.3)
    axes[2].set_title('Mining Status & Hashrate')
    
    # GPU temperature
    axes[3].plot(df['timestamp'], df['gpu_temp_c'], label='GPU Temperature', color='red')
    axes[3].set_ylabel('Temperature (°C)')
    axes[3].set_xlabel('Time')
    axes[3].legend(loc='upper left')
    axes[3].grid(True, alpha=0.3)
    axes[3].set_title('GPU Temperature')
    
    plt.tight_layout()
    plt.savefig('logs/solar_mining_analysis.png', dpi=150)
    print("📊 Plot saved: logs/solar_mining_analysis.png")
    plt.show()

def plot_daily_pattern(df):
    """Display daily patterns."""
    df['hour'] = df['timestamp'].dt.hour
    
    hourly = df.groupby('hour').agg({
        'solar_production_w': 'mean',
        'house_consumption_w': 'mean',
        'available_for_mining_w': 'mean',
        'mining_active': 'mean',
        'hashrate_mhs': 'mean'
    })
    
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    
    # Power profile
    axes[0].plot(hourly.index, hourly['solar_production_w'], marker='o', label='Solar Production')
    axes[0].plot(hourly.index, hourly['house_consumption_w'], marker='s', label='House Consumption')
    axes[0].plot(hourly.index, hourly['available_for_mining_w'], marker='^', label='Available')
    axes[0].set_ylabel('Power (W)')
    axes[0].set_xlabel('Hour')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title('Average Daily Profile')
    axes[0].set_xticks(range(24))
    
    # Mining activity
    axes[1].bar(hourly.index, hourly['mining_active']*100, alpha=0.6, label='Mining Activity (%)')
    ax1_right = axes[1].twinx()
    ax1_right.plot(hourly.index, hourly['hashrate_mhs'], marker='o', color='red', 
                   linewidth=2, label='Hashrate')
    axes[1].set_ylabel('Mining Activity (%)')
    ax1_right.set_ylabel('Hashrate (MH/s)', color='red')
    ax1_right.tick_params(axis='y', labelcolor='red')
    axes[1].set_xlabel('Hour')
    axes[1].legend(loc='upper left')
    ax1_right.legend(loc='upper right')
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xticks(range(24))
    
    plt.tight_layout()
    plt.savefig('logs/daily_pattern.png', dpi=150)
    print("📊 Plot saved: logs/daily_pattern.png")
    plt.show()

def export_for_ml(df):
    """Export data for ML training."""
    # Prepare features for ML
    ml_df = df.copy()
    ml_df['hour'] = ml_df['timestamp'].dt.hour
    ml_df['minute'] = ml_df['timestamp'].dt.minute
    ml_df['day_of_week'] = ml_df['timestamp'].dt.dayofweek
    ml_df['month'] = ml_df['timestamp'].dt.month
    
    # Only relevant columns
    features = [
        'hour', 'minute', 'day_of_week', 'month',
        'solar_production_w', 'house_consumption_w', 
        'grid_power_w', 'available_for_mining_w',
        'gpu_usage_percent', 'gpu_temp_c',
        'mining_active'  # Target variable
    ]
    
    ml_df[features].to_csv('logs/ml_training_data.csv', index=False)
    print("🤖 ML training data saved: logs/ml_training_data.csv")

if __name__ == "__main__":
    print("🔍 Loading Solar Mining data...\n")
    
    df = load_data()
    if df is None:
        exit(1)
    
    show_statistics(df)
    
    try:
        print("\n📊 Creating plots...")
        plot_overview(df)
        plot_daily_pattern(df)
        export_for_ml(df)
    except ImportError:
        print("⚠️  matplotlib/pandas not installed - only statistics shown")
        print("   Installation: pip install pandas matplotlib")
