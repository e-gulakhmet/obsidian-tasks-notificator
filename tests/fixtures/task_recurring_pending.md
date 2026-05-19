---
title: Recurring Daily Standup
status: done
priority: normal
scheduled: 2026-05-19T09:00
recurrence: DTSTART:20260518T090000;FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
recurrence_anchor: scheduled
complete_instances:
  - 2026-05-18
skipped_instances: []
reminders:
  - id: rem_001
    type: relative
    relatedTo: scheduled
    offset: -PT10M
    description: 10 minutes before
---
