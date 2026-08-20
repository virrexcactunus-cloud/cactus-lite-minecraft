"""RAM option list: what can be picked, what is recommended, what is taken."""

from cactus_lite.core.platform_utils import ram_info, total_ram_gb

SUFFIX_RECOMMENDED = " (рекомендовано)"
SUFFIX_BUSY = " (заняты)"


def options():
    """Return (labels, values, selectable_set, recommended_gb)."""
    total, avail = ram_info()
    total = max(total, total_ram_gb(), 1)
    values = list(range(1, total + 1))
    selectable = [v for v in values if v <= avail] or [1]
    recommended = min(max(total // 2, 1), selectable[-1])
    recommended = max(recommended, selectable[0])
    labels = []
    for value in values:
        if value in selectable:
            labels.append(f"{value} ГБ" + (SUFFIX_RECOMMENDED if value == recommended else ""))
        else:
            labels.append(f"{value} ГБ" + SUFFIX_BUSY)
    return labels, values, set(selectable), recommended


def label_for(value, recommended, selectable):
    if value not in selectable:
        return f"{value} ГБ" + SUFFIX_BUSY
    return f"{value} ГБ" + (SUFFIX_RECOMMENDED if value == recommended else "")


def parse(label, values):
    digits = ""
    for ch in label or "":
        if ch.isdigit():
            digits += ch
        else:
            break
    if not digits:
        return None
    value = int(digits)
    return value if value in values else None
