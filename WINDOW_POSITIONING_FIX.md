# Window Positioning Fix for PyQt6 Compatibility

## Issue Description

When running TOI with PyQt6, windows open at "default" positions (starting from top-left with small offsets) instead of the specific positions that work correctly with PyQt5. All windows lose their carefully calculated positioning.

## Root Cause

The issue is in the PyQt6 compatibility layer at `PyQtX/QtWidgets.py`:

**Original Code (Line 12):**
```python
return screens[index].geometry()
```

**Problem:** 
- In PyQt5, `QDesktopWidget().screenGeometry()` returns the **available geometry** (screen area excluding taskbars, panels, dock, etc.)
- The PyQt6 compatibility implementation was using `screens[index].geometry()` which returns the **full screen geometry** (entire screen including areas covered by system UI)
- This caused all position calculations to be incorrect, resulting in windows appearing at default positions

## Solution

Changed line 12 in `PyQtX/QtWidgets.py` from:
```python
return screens[index].geometry()
```

To:
```python
return screens[index].availableGeometry()
```

**Why this works:**
- `availableGeometry()` returns the screen area minus system UI elements
- This matches the behavior of PyQt5's `QDesktopWidget().screenGeometry()`
- Window position calculations in `toi.py` (lines 3654-3657) now work correctly with both PyQt5 and PyQt6

## Files Modified

- `PyQtX/QtWidgets.py` - Fixed QDesktopWidget compatibility class

## Files Using Window Geometry

The following files use the geometry variables for window positioning:
- `obs_gui.py` - Uses `obs_window_geometry`
- `mnt_gui.py` - Uses `mnt_geometry`
- `instrument_gui.py` - Uses `instrument_geometry`
- `plan_gui.py` - Uses `plan_geometry`
- `sky_gui.py` - Uses `obs_window_geometry`
- `guider_gui.py` - Uses `obs_window_geometry`
- `focus_gui.py` - Uses `obs_window_geometry`
- `fits_gui.py` - Uses `obs_window_geometry`
- `flat_gui.py` - Uses `obs_window_geometry`
- `planrunner_gui.py` - Uses `obs_window_geometry`
- `conditions_gui.py` - Uses `obs_window_geometry`

## Testing Notes

To verify the fix:
1. Run TOI with PyQt6
2. Check that windows open at their specific calculated positions
3. Main window should be at screen top-left
4. Mount window should be below main window with 110px offset
5. Instrument window should be to the right with specific offsets
6. Plan window should be further right
7. All positions should respect screen available area (not covered by taskbars/panels)

## Compatibility

This fix maintains full backward compatibility with PyQt5 while fixing the PyQt6 behavior.
