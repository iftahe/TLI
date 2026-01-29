import sys
import os
import zoneinfo

# Add src to path
sys.path.append(os.getcwd())

try:
    from src.bot.utils import get_now, to_naive_israel
    from src.scheduler.service import scheduler
    
    print("Imports successful.")
    
    now = get_now()
    print(f"Current Israel time: {now}")
    print(f"Timezone: {now.tzinfo}")
    
    assert str(now.tzinfo) == "Asia/Jerusalem"
    
    naive = to_naive_israel(now)
    print(f"Naive time: {naive}")
    assert naive.tzinfo is None
    
    print(f"Scheduler timezone: {scheduler.timezone}")
    assert str(scheduler.timezone) == "Asia/Jerusalem"
    
    print("Verification passed!")
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Verification failed: {e}")
    sys.exit(1)
