
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

def resolve_filed_name_array(var_type: dict) -> Tuple[str,  Optional[int]]:
  if var_type is None:
    return None, None
  
  s = str(var_type).strip()
  m = re.match(r"^\s*(.*?)\s*\[\s*(\d*)\s*\]\s*$", s)
  base = s
  if m:
    base = m.group(1).strip()
    size_str = m.group(2)
    if size_str == "":
      raise ValueError(f"Array size missing in field var_type '{var_type}'")
    try:
      size = int(size_str)
    except Exception:
      raise ValueError(f"Invalid array size '{size_str}' in field var_type '{var_type}'")
    return (base, size)
  return base, None


def is_base_type(var_type: str) -> bool:
  BASE_TYPES = (
    "int8", "uint8",
    "int16", "uint16",
    "int32", "uint32",
    "int64", "uint64",
    "float", "double",
    "bool", "char"
  )
  """Check if var_type is a base type or an array of base types."""
  if var_type is None:
    return False
  if var_type in BASE_TYPES:
    return True
  return False