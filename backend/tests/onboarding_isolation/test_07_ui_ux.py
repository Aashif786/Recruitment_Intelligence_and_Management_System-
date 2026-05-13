
import os

def test_ui_ux_responsive_audit():
    path = "c:/Users/user/Desktop/RIMS/rims/frontend/app/dashboard/onboarding/page.tsx"
    if not os.path.exists(path):
        pytest.skip("Frontend source not found")
        
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check for responsive grid
    assert "grid-cols-1 md:grid-cols-3" in content
    # Check for mobile scroll
    assert "overflow-x-auto" in content
    # Check for professional fonts (inherited from layout but used in components)
    assert "font-black" in content or "font-bold" in content
