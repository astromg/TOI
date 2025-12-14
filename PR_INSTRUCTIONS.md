# Pull Request Instructions

## Important: PR Target Branch

⚠️ **This PR MUST target the `updeps` branch, NOT `main` or `master`.**

The `updeps` branch contains the PyQt6 migration work, and this fix is specifically for PyQt6 compatibility.

## Branch Structure

```
main/master (PyQt5)
  └── updeps (PyQt6 migration) ← TARGET THIS BRANCH
       └── copilot/fix-window-positioning (this fix)
```

## Creating the PR

When creating the pull request on GitHub:

1. **Base branch**: `updeps`
2. **Compare branch**: `copilot/fix-window-positioning`

## Summary of Changes

This PR fixes window positioning issues when running TOI with PyQt6.

### Files Changed:
- `PyQtX/QtWidgets.py` - Fixed QDesktopWidget compatibility to use availableGeometry()
- `WINDOW_POSITIONING_FIX.md` - Documentation of the issue and fix

### The Fix:
Changed one line in the PyQt6 compatibility layer from:
```python
return screens[index].geometry()  # Wrong - returns full screen
```
To:
```python
return screens[index].availableGeometry()  # Correct - excludes taskbars
```

This ensures window positions are calculated correctly, matching PyQt5 behavior.

## Testing

Manual testing required with PyQt6 to verify:
1. All windows open at their specific calculated positions
2. Windows respect screen boundaries and taskbar areas
3. Backward compatibility with PyQt5 is maintained

## Related Issue

Closes issue about window positioning being "default" (top-left with small offset) instead of specific positions when running with PyQt6.
