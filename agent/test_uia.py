"""Test: detect toast notification windows via UI Automation."""
import ctypes
import ctypes.wintypes
import comtypes
import comtypes.client
from comtypes import GUID
import time

# Load UIAutomationCore
UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
uia = comtypes.CoCreateInstance(
    GUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}"),  # CUIAutomation
    interface=UIAutomationCore.IUIAutomation,
)

root = uia.GetRootElement()

# Property IDs
UIA_ClassNamePropertyId = 30012
UIA_NamePropertyId = 30005
UIA_AutomationIdPropertyId = 30011
UIA_ControlTypePropertyId = 30003

# Look for toast notification windows
# Windows toast notifications typically have ClassName "Windows.UI.Core.CoreWindow"
# and are in the notification area

# Create condition for ClassName = "Windows.UI.Core.CoreWindow"
cond_class = uia.CreatePropertyCondition(
    UIA_ClassNamePropertyId,
    "Windows.UI.Core.CoreWindow"
)

print("Searching for CoreWindow elements...")
elements = root.FindAll(UIAutomationCore.TreeScope_Children, cond_class)
for i in range(elements.Length):
    el = elements.GetElement(i)
    name = el.CurrentName
    auto_id = el.GetCurrentPropertyValue(UIA_AutomationIdPropertyId)
    print(f"  CoreWindow: Name='{name}', AutomationId='{auto_id}'")

# Also look for notification-related windows
print("\nSearching for 'notification' in top-level windows...")
true_cond = uia.CreateTrueCondition()
all_children = root.FindAll(UIAutomationCore.TreeScope_Children, true_cond)
for i in range(all_children.Length):
    el = all_children.GetElement(i)
    name = el.CurrentName or ""
    cls = el.GetCurrentPropertyValue(UIA_ClassNamePropertyId) or ""
    if "notif" in name.lower() or "notif" in cls.lower() or "toast" in name.lower() or "toast" in cls.lower():
        print(f"  Name='{name}', ClassName='{cls}'")

# Look specifically for the Action Center / Notification Center
print("\nSearching for 'New Notification' or 'ActionCenter' elements...")
for i in range(all_children.Length):
    el = all_children.GetElement(i)
    name = el.CurrentName or ""
    cls = el.GetCurrentPropertyValue(UIA_ClassNamePropertyId) or ""
    auto_id = el.GetCurrentPropertyValue(UIA_AutomationIdPropertyId) or ""
    if any(kw in f"{name}{cls}{auto_id}".lower() for kw in ["action", "notif", "toast", "shell_"]):
        print(f"  Name='{name}', ClassName='{cls}', AutomationId='{auto_id}'")

print("\nDone. To test with a live toast, trigger a notification and run this script again quickly.")
