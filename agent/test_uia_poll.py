"""Test: continuously poll for toast notification windows via UI Automation.
Run this script, then trigger a Teams notification within 60 seconds."""

import ctypes
import ctypes.wintypes
import time

# Use FindWindowW / EnumChildWindows approach
user32 = ctypes.windll.user32
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.wintypes.HWND
user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]

def get_window_text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value

def get_class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def find_toast_windows():
    """Find all windows that might be toast notifications."""
    results = []
    def callback(hwnd, lparam):
        cls = get_class_name(hwnd)
        title = get_window_text(hwnd)
        # Toast notification related class names
        if any(kw in cls.lower() for kw in ["toast", "notif", "corewindow"]):
            results.append((hwnd, cls, title))
        elif any(kw in title.lower() for kw in ["notification", "通知"]):
            results.append((hwnd, cls, title))
        return True
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results

# Also try with UI Automation for richer info
import comtypes
import comtypes.client
from comtypes import GUID

UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
uia = comtypes.CoCreateInstance(
    GUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}"),
    interface=UIAutomationCore.IUIAutomation,
)

UIA_ClassNamePropertyId = 30012
UIA_NamePropertyId = 30005
UIA_AutomationIdPropertyId = 30011

def find_uia_toasts():
    """Find toast elements via UIA tree."""
    root = uia.GetRootElement()
    true_cond = uia.CreateTrueCondition()
    children = root.FindAll(UIAutomationCore.TreeScope_Children, true_cond)
    
    found = []
    for i in range(children.Length):
        el = children.GetElement(i)
        name = el.CurrentName or ""
        cls = el.GetCurrentPropertyValue(UIA_ClassNamePropertyId) or ""
        aid = el.GetCurrentPropertyValue(UIA_AutomationIdPropertyId) or ""
        
        if any(kw in f"{name}{cls}{aid}".lower() for kw in [
            "toast", "notif", "notification", "通知",
            "new notification", "actioncenter"
        ]):
            found.append({"name": name, "class": cls, "automationId": aid})
            
            # Try to get child text elements
            try:
                text_children = el.FindAll(UIAutomationCore.TreeScope_Descendants, true_cond)
                texts = []
                for j in range(min(text_children.Length, 50)):
                    child = text_children.GetElement(j)
                    child_name = child.CurrentName or ""
                    if child_name:
                        texts.append(child_name)
                if texts:
                    found[-1]["texts"] = texts
            except:
                pass
    return found

print("Polling for toast windows every 1s (Ctrl+C to stop)...")
print(">>> Please trigger a Teams (or any) notification now! <<<\n")

seen_hwnds = set()
tick = 0
try:
    while True:
        # Win32 approach
        toasts = find_toast_windows()
        for hwnd, cls, title in toasts:
            if hwnd not in seen_hwnds:
                seen_hwnds.add(hwnd)
                print(f"[{tick}s] Win32: hwnd={hwnd}, class='{cls}', title='{title}'")
        
        # UIA approach
        uia_toasts = find_uia_toasts()
        for t in uia_toasts:
            key = f"{t['name']}|{t['class']}"
            if key not in seen_hwnds:
                seen_hwnds.add(key)
                print(f"[{tick}s] UIA: name='{t['name']}', class='{t['class']}', aid='{t.get('automationId', '')}'" )
                if "texts" in t:
                    print(f"       Texts: {t['texts'][:10]}")
        
        time.sleep(1)
        tick += 1
except KeyboardInterrupt:
    print("\nStopped.")

