import sys
import os
# Add backend to path so we can import interview_process
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from interview_process.utils import calculate_experience_years

def test_experience_calculation():
    # User's example data
    # IBM: Aug 27, 2008 – July 2, 2011 (~2.8 years)
    # SAP: July 4, 2011 – Sep 30, 2014 (~3.2 years)
    # Dhoot: July 25, 2024 – May 8, 2024 (Correction: May 8, 2024 – July 25, 2024) (~0.2 years)
    # Gap: Oct 2014 - May 2024 (~9.6 years) -> Should be ignored
    
    roles = [
        {"start_date": "27th Aug 2008", "end_date": "2nd July 2011"},
        {"start_date": "4th July 2011", "end_date": "30th September 2014"},
        {"start_date": "25th July 2024", "end_date": "8th May 2024"} # Swapped to test auto-correction
    ]
    
    total_years = calculate_experience_years(roles)
    
    print(f"Roles provided: {len(roles)}")
    print(f"Total Experience Calculated: {total_years} years")
    
    # Expected: ~2.8 + ~3.2 + ~0.2 = ~6.2 years
    # The 10 year gap should be ignored.
    
    if 6.0 <= total_years <= 6.5:
        print("SUCCESS: Experience calculation correctly handled gaps and typos!")
    else:
        print(f"FAILURE: Expected around 6.2 years, but got {total_years}")

if __name__ == "__main__":
    test_experience_calculation()
