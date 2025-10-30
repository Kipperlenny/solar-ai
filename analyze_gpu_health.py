"""
GPU Health Log Analyzer
========================
Analyzes logs/gpu_health.csv to identify patterns in GPU stuck events.

Answers questions like:
- Which GPU gets stuck most often?
- Which algorithm causes most stucks?
- Is one GPU always stuck with a specific algorithm?
- What's the recovery success rate?
"""

import csv
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

GPU_HEALTH_LOG = Path("logs/gpu_health.csv")

def analyze_gpu_health():
    """Analyze GPU health log and print detailed statistics."""
    
    if not GPU_HEALTH_LOG.exists():
        print(f"❌ GPU health log not found: {GPU_HEALTH_LOG}")
        print(f"   The log will be created once the mining script runs with GPU health monitoring.")
        return
    
    # Read all events
    events = []
    with open(GPU_HEALTH_LOG, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(row)
    
    if not events:
        print("ℹ️  No GPU health events logged yet.")
        return
    
    print("=" * 80)
    print("📊 GPU HEALTH ANALYSIS REPORT")
    print("=" * 80)
    print(f"\nTotal Events: {len(events)}")
    print(f"Date Range: {events[0]['timestamp']} to {events[-1]['timestamp']}")
    print()
    
    # Statistics by event type
    event_counts = Counter(e['event_type'] for e in events)
    print("=" * 80)
    print("📋 EVENT SUMMARY")
    print("=" * 80)
    for event_type, count in event_counts.most_common():
        print(f"  {event_type:20s}: {count:4d}")
    print()
    
    # GPU-specific analysis
    gpu_stats = defaultdict(lambda: {
        'stuck_count': 0,
        'fix_attempted': 0,
        'fix_success': 0,
        'fix_failed': 0,
        'recovered': 0,
        'total_stuck_duration': 0,
        'stuck_algorithms': Counter()
    })
    
    for event in events:
        gpu_id = event['gpu_id']
        event_type = event['event_type']
        
        if event_type == 'stuck_detected':
            gpu_stats[gpu_id]['stuck_count'] += 1
            gpu_stats[gpu_id]['stuck_algorithms'][event['stuck_algorithm']] += 1
        elif event_type == 'fix_attempted':
            gpu_stats[gpu_id]['fix_attempted'] += 1
            if event['stuck_duration_seconds']:
                gpu_stats[gpu_id]['total_stuck_duration'] += int(event['stuck_duration_seconds'])
        elif event_type == 'fix_success':
            gpu_stats[gpu_id]['fix_success'] += 1
        elif event_type == 'fix_failed':
            gpu_stats[gpu_id]['fix_failed'] += 1
        elif event_type == 'recovered':
            gpu_stats[gpu_id]['recovered'] += 1
    
    print("=" * 80)
    print("🖥️  GPU-SPECIFIC ANALYSIS")
    print("=" * 80)
    
    for gpu_id in sorted(gpu_stats.keys()):
        stats = gpu_stats[gpu_id]
        
        # Get GPU name from first event
        gpu_name = next((e['gpu_name'] for e in events if e['gpu_id'] == gpu_id), f"GPU {gpu_id}")
        
        print(f"\n{gpu_name} (ID: {gpu_id})")
        print(f"  {'Stuck Detections:':<25} {stats['stuck_count']}")
        print(f"  {'Fix Attempts:':<25} {stats['fix_attempted']}")
        print(f"  {'Successful Fixes:':<25} {stats['fix_success']}")
        print(f"  {'Failed Fixes:':<25} {stats['fix_failed']}")
        print(f"  {'Recoveries:':<25} {stats['recovered']}")
        
        if stats['fix_attempted'] > 0:
            success_rate = (stats['fix_success'] / stats['fix_attempted']) * 100
            print(f"  {'Success Rate:':<25} {success_rate:.1f}%")
            
            avg_duration = stats['total_stuck_duration'] / stats['fix_attempted']
            print(f"  {'Avg Stuck Duration:':<25} {avg_duration/60:.1f} minutes")
        
        if stats['stuck_algorithms']:
            print(f"  {'Problem Algorithms:':}")
            for algo, count in stats['stuck_algorithms'].most_common():
                print(f"    - {algo:<20}: {count} times")
    
    print()
    
    # Algorithm-specific analysis
    algorithm_stats = defaultdict(lambda: {
        'stuck_count': 0,
        'affected_gpus': set()
    })
    
    for event in events:
        if event['event_type'] == 'stuck_detected':
            algo = event['stuck_algorithm']
            algorithm_stats[algo]['stuck_count'] += 1
            algorithm_stats[algo]['affected_gpus'].add(event['gpu_id'])
    
    print("=" * 80)
    print("🔧 ALGORITHM COMPATIBILITY ANALYSIS")
    print("=" * 80)
    
    # Sort by most problematic
    sorted_algos = sorted(algorithm_stats.items(), key=lambda x: x[1]['stuck_count'], reverse=True)
    
    if sorted_algos:
        print("\nMost Problematic Algorithms:")
        for algo, stats in sorted_algos:
            affected = ', '.join(sorted(stats['affected_gpus']))
            print(f"  {algo:<20}: {stats['stuck_count']} stuck events (GPUs: {affected})")
    else:
        print("\n✅ No problematic algorithms detected!")
    
    print()
    
    # GPU-Algorithm compatibility matrix
    print("=" * 80)
    print("🔍 GPU-ALGORITHM COMPATIBILITY MATRIX")
    print("=" * 80)
    
    gpu_algo_matrix = defaultdict(lambda: defaultdict(int))
    
    for event in events:
        if event['event_type'] == 'stuck_detected':
            gpu_id = event['gpu_id']
            algo = event['stuck_algorithm']
            gpu_algo_matrix[gpu_id][algo] += 1
    
    if gpu_algo_matrix:
        print("\nStuck Events per GPU-Algorithm Combination:")
        print()
        
        # Get all unique algorithms
        all_algos = set()
        for algos in gpu_algo_matrix.values():
            all_algos.update(algos.keys())
        
        # Print header
        print(f"{'GPU ID':<15}", end="")
        for algo in sorted(all_algos):
            print(f"{algo:<15}", end="")
        print()
        print("-" * (15 + 15 * len(all_algos)))
        
        # Print matrix
        for gpu_id in sorted(gpu_algo_matrix.keys()):
            gpu_name = next((e['gpu_name'] for e in events if e['gpu_id'] == gpu_id), f"GPU {gpu_id}")
            print(f"{gpu_name[:14]:<15}", end="")
            for algo in sorted(all_algos):
                count = gpu_algo_matrix[gpu_id].get(algo, 0)
                if count > 0:
                    print(f"{count:<15}", end="")
                else:
                    print(f"{'-':<15}", end="")
            print()
    else:
        print("\n✅ No stuck events to analyze!")
    
    print()
    
    # Recommendations
    print("=" * 80)
    print("💡 RECOMMENDATIONS")
    print("=" * 80)
    print()
    
    # Find consistently problematic GPU-algorithm combinations
    for gpu_id, algos in gpu_algo_matrix.items():
        gpu_name = next((e['gpu_name'] for e in events if e['gpu_id'] == gpu_id), f"GPU {gpu_id}")
        for algo, count in algos.items():
            if count >= 3:  # If stuck 3+ times
                print(f"⚠️  {gpu_name} frequently gets stuck on {algo} ({count} times)")
                print(f"   Consider adding {algo} to QuickMiner's disabledAlgo list for this GPU")
                print()
    
    if not any(count >= 3 for algos in gpu_algo_matrix.values() for count in algos.values()):
        print("✅ No recurring GPU-algorithm compatibility issues detected!")
        print("   The auto-fix system is working well!")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    analyze_gpu_health()
