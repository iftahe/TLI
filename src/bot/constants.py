# States
(
    DESCRIPTION,
    PRIORITY,
    SUB_CATEGORY,
    REMINDER
) = range(4)

# Callback Data Prefixes and Values
PRIORITY_URGENT = 'urgent'
PRIORITY_NORMAL = 'normal'
PRIORITY_LOW = 'low'

REMINDER_1H = 'reminder_1h'
REMINDER_TONIGHT = 'reminder_tonight'
REMINDER_TOMORROW = 'reminder_tomorrow'
REMINDER_MORNING_930 = 'reminder_morning_930'
REMINDER_3D = 'reminder_3d'
REMINDER_1W = 'reminder_1w'
REMINDER_NONE = 'reminder_none'

SNOOZE_1H_PREFIX = 'snooze_1h_'

CATEGORY_HOME = 'home'
CATEGORY_WORK = 'work'

# Valid Callbacks Prefixes
VIEW_TASK = 'view_task_'
DONE_TASK = 'done_task_'
EDIT_TASK = 'edit_task_'
EDIT_REMINDER_PREFIX = 'edit_rem_'
UPD_REMINDER_PREFIX = 'upd_rem_'

# Edit State
EDITING_DESCRIPTION = 10
