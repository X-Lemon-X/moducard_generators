"""Utilities to read module/type YAML configs.

The loader supports:
- Multiple YAML files at once.
- Optional ``include`` directives (string or list) to pull in shared type files.
- Auto-classification: a file with ``hardware`` is treated as a module; otherwise
  it is treated as a type library.

Example:
  loader = ConfigLoader({"base_types": "./base_types.yaml"})
  loader.load_files(["example_module_config.yaml"])
  module = loader.get_module("motor_hat")
  types = loader.types  # merged custom types from all files
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from datetime import datetime
import yaml
import enum
import shutil

from config_helpers import resolve_filed_name_array, is_base_type


@dataclass
class ModuleConfig:
  path: Path
  hardware: HardwareInfo
  messages: Dict[str, Dict[str, MessageInfo]]
  custom_types: Dict[str, TypeDefinition]  
  includes: List[str] = field(default_factory=list)

  def __str__(self) -> str:
    """Return string representation of ModuleConfig."""
    return (
      f"ModuleConfig(path={self.path.name}, "
      f"hardware={self.hardware.name}"
    )

@dataclass
class TypeModule:
  """Represents a loaded YAML file without hardware (type definitions only)."""
  path: Path
  origin: str  # filename stem or include name
  messages: Dict[str, Dict[str, MessageInfo]] = field(default_factory=dict)  # {group -> {msg_name -> MessageInfo}}
  custom_types: Dict[str, TypeDefinition] = field(default_factory=dict)  # parsed types
  includes: List[str] = field(default_factory=list)

  def __str__(self) -> str:
    """Return string representation of TypeModule."""
    msg_counts = {group: len(msgs) for group, msgs in self.messages.items()}
    return (
      f"TypeModule(path={self.path.name}, "
      f"origin={self.origin}"
    )

@dataclass
class MessageInfo:
  """Complete message descriptor with metadata and validation."""
  name: str
  var_type: str
  description: Optional[str] = None
  readable_name: Optional[str] = None
  default: Optional[object] = None
  units: Optional[str] = None
  range: Optional[List] = None
  permission_read: bool = True
  permission_write: bool = False
  can_id: Optional[str] = None
  array_size: Optional[int] = None
  ros_mapping: Optional[str] = None
  arg: Optional[str] = None 
  group: Optional[str] = None

  @classmethod
  def from_dict(cls, name: str, data: dict, group) -> MessageInfo:
    """Create MessageInfo from YAML dict, validates required fields."""
    if "var_type" not in data:
      raise ValueError(f"Message '{name}' missing required field 'var_type'")
    filed_name, array_size = resolve_filed_name_array(data["var_type"])
    if filed_name is None:
      raise ValueError(f"Message '{name}' has invalid var_type '{data['var_type']}'")
    per_read, per_write = cls._permission_from_string(data.get("permission"))
    return cls(
      name=name,
      var_type=filed_name,
      description=data.get("description"),
      readable_name=data.get("readable_name"),
      default=data.get("default"),
      units=data.get("units"),
      range=data.get("range"),
      permission_read=per_read,
      permission_write=per_write,
      can_id=data.get("id"),
      array_size=array_size,
      ros_mapping=data.get("ros_mapping"),
      arg=data.get("arg"),
      group=group,
    )

  @classmethod
  def _permission_from_string(cls,s) :
    if s is None:
      return True, True
    s = s.lower()
    if s == "r":
      return True, False
    elif s == "w":
      return False, True
    elif s == "rw" or s == "wr":
      return True, True
    else:
      raise ValueError(f"Invalid permission string: {s}")

@dataclass
class TypeField:
  """Field definition inside a struct-type custom type."""
  name: str
  var_type: str
  description: Optional[str] = None
  units: Optional[str] = None
  default: Optional[object] = None
  range: Optional[List] = None
  array_size: Optional[int] = None
  ros_mapping: Optional[str] = None
  arg: Optional[str] = None

  @classmethod
  def from_dict(cls, name: str, data: dict) -> TypeField:
    """Create TypeField from YAML dict, validates required fields."""
    if "var_type" not in data:
      raise ValueError(f"Field '{name}' missing required field 'var_type'")
    filed_name, array_size = resolve_filed_name_array(data["var_type"])
    if filed_name is None:
      raise ValueError(f"Message '{name}' has invalid var_type '{data['var_type']}'")
    return cls(
      name=name,
      var_type=filed_name,
      description=data.get("description"),
      units=data.get("units"),
      default=data.get("default"),
      range=data.get("range"),
      array_size=array_size,
      ros_mapping=data.get("ros_mapping"),
      arg=data.get("arg"),
    )

@dataclass
class TypeDefinition:
  """Normalized representation of a custom type definition."""
  name: str
  kind: str
  readable_name: Optional[str] = None
  description: Optional[str] = None
  fields: Dict[str, TypeField] = field(default_factory=dict)
  values: Dict[str, str] = field(default_factory=dict)
  raw: dict = field(default_factory=dict)
  ros_mapping: Optional[str] = None

  @classmethod
  def from_dict(cls, name: str, data: dict) -> TypeDefinition:
    """Create TypeDefinition from YAML dict, validates required fields."""
    if "type" not in data:
      raise ValueError(f"Type '{name}' missing required field 'type'")

    fields = {}
    values = {}
    if data["type"] == "struct":
      if "fields" not in data:
        raise ValueError(f"Struct type '{name}' missing required field 'fields'")
      if "values" in data:
        raise ValueError(f"Struct type '{name}' should not have 'values' field")
      
      raw_fields = data.get("fields", {})
      for field_name, field_data in raw_fields.items():
        fields[field_name] = TypeField.from_dict(field_name, field_data)

    elif data["type"] == "enum":
      if "fields" in data:
        raise ValueError(f"Enum type '{name}' should not have 'fields' field")
      if "values" not in data:
        raise ValueError(f"Enum type '{name}' missing required field 'values'")
      raw_values = data.get("values", {})
      for val_name, val_desc in raw_values.items():
        if not isinstance(val_desc, str):
          raise ValueError(f"Enum value '{val_name}' in type '{name}' must have a string description")
        if val_name in values:
          raise ValueError(f"Enum type '{name}' has duplicate value name '{val_name}'")
        values[val_name] = val_desc
    else:
      raise ValueError(f"Type '{name}' has unknown type '{data['type']}', expected 'struct' or 'enum'")

    return cls(
      name=name,
      kind=data["type"],
      readable_name=data.get("readable_name"),
      description=data.get("description"),
      fields=fields,
      values=values,
      raw=data,
      ros_mapping=data.get("ros_mapping"),
    )

@dataclass
class HardwareInfo:
  name: str
  unique_id: str
  hw_revision: int = 0
  fw_revision: int = 0
  date: int =0
  description: str = "" 
  inherit: List[str] = field(default_factory=list)
  vendor: Optional[str] = None

  @classmethod
  def from_dict(cls, data: dict) -> HardwareInfo:
    """Create HardwareInfo from YAML dict, validates required fields."""
    if "name" not in data:
      raise ValueError("Hardware config missing required field 'name'")
    if "unique_id" not in data:
      raise ValueError("Hardware config missing required field 'unique_id'")
    
    fw_version = data.get("fw_revision", 0)
    if fw_version is None:
      fw_version = 0
    hw_revision = data.get("hw_revision", 0)
    if hw_revision is None:
      hw_revision = 0 
    date = data.get("date", 0)
    if date is None:
      date = 0
    else:
      try:
        date = int(datetime.strptime(str(date), "%Y-%m-%d").timestamp())
      except Exception as e:
        raise ValueError(f"Invalid date format: {data['date']}, expected YYYY-MM-DD \n Error: {e}")

    description = data.get("description", "")
    if description is None:
      description = ""

    return cls(
      name=data["name"],
      hw_revision=hw_revision,
      fw_revision=fw_version,
      date=date,
      description=description,
      unique_id=data.get("unique_id", ""),
      inherit=data.get("inherit", []),
      vendor=data.get("vendor"),
    )


class ConfigLoader:
  """Load module configs and shared type YAMLs with simple include support."""

  def __init__(self, include_dirs: Optional[Sequence[str | Path]] = None) -> None:
    """Initialize ConfigLoader with directories to search for include files.
    
    Args:
      include_dirs: List of directories to search for include files.
                    When an include is referenced, the loader will search
                    these directories for matching .yaml/.yml files.
    """
    self.include_dirs: List[Path] = [
      Path(d).resolve() for d in (include_dirs or [])
    ]
    self.modules: List[ModuleConfig] = []
    self.type_modules: List[TypeModule] = []
    self._include_cache: Dict[str, Path] = {}  # cache for found includes

  def get_modules(self) -> List[ModuleConfig]:
    return self.modules

  def get_type_modules(self) -> List[TypeModule]:
    return self.type_modules

  def load_files(self, files: Iterable[str | Path]) -> None:
    visited: Set[Path] = set()
    for file_path in files:
      self._load_file(Path(file_path).resolve(), visited)

  # Internal helpers ---------------------------------------------------
  def _find_include_file(self, include_name: str) -> Optional[Path]:
    """Search include_dirs for a file matching include_name.
    
    Tries: include_name.yaml, include_name.yml, include_name (as-is)
    Returns: Resolved path if found, None otherwise
    """
    if include_name in self._include_cache:
      return self._include_cache[include_name]
    
    for dir_path in self.include_dirs:
      candidate = dir_path / f"{include_name}.yaml"
      if candidate.exists() and candidate.is_file():
        self._include_cache[include_name] = candidate.resolve()
        return candidate.resolve()
    return None

  def _load_file(self, path: Path, visited: Set[Path], as_include:bool=False, include_name:Optional[str]=None) -> None:
    if path in visited:
      return
    visited.add(path)

    data = self._load_yaml(path)
    includes = self._normalize_includes(data.get("include"))

    for inc in includes:
      inc_path = self._find_include_file(inc)
      if inc_path:
        # pass include name so we can record types/messages under that include
        self._load_file(inc_path, visited, as_include=True, include_name=inc)
      else:
        raise ValueError(f"Warning: Could not find include '{inc}' in search directories: {self.include_dirs}")
        

    if "hardware" in data: # Module with hardware config
      if as_include:
        raise ValueError(f"Include file '{path}' cannot define hardware config")
      hardware_info = HardwareInfo.from_dict(data["hardware"])
      messages_raw = data.get("messages", {})
      custom_types_raw = data.get("custom_types", {})

      # Collect inherited messages and merge with module messages
      inherited_messages = self._collect_inherited_messages(hardware_info.inherit)
      module_messages = self._parse_message_groups(messages_raw)
      merged_messages = self._merge_inherited_messages(module_messages, inherited_messages)
      
      parsed_types = self._parse_type_definitions(custom_types_raw)
      module = ModuleConfig(
        path=path,
        hardware=hardware_info,
        messages=merged_messages,
        custom_types=parsed_types,
        includes=includes,
      )
      self.modules.append(module)
    else: # No hardware -> type module
      custom_types_raw = data.get("custom_types", {})
      messages_raw = data.get("messages", {})
      
      if as_include and include_name:
        origin = include_name
      else:
        # loaded directly (not as a named include) -- use filename stem as origin
        origin = path.stem
      parsed_types = self._parse_type_definitions(custom_types_raw)
      parsed_messages = self._parse_message_groups(messages_raw)      
      # Create TypeModule object storing parsed types and messages directly
      type_module = TypeModule(
        path=path,
        origin=origin,
        custom_types=parsed_types,
        messages=parsed_messages,
        includes=includes,
      )
      self.type_modules.append(type_module)

  def _load_yaml(self, path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
      return yaml.safe_load(fh) or {}

  def _extract_includes(self, path: Path) -> List[str]:
    includes: List[str] = []
    pattern = re.compile(r"^\s*include:\s*(\S+)")
    with path.open("r", encoding="utf-8") as fh:
      for line in fh:
        match = pattern.match(line)
        if match:
          includes.append(match.group(1))
    return includes

  def _normalize_includes(self, raw: object) -> List[str]:
    if raw is None:
      return []
    if isinstance(raw, str):
      return [raw]
    if isinstance(raw, list):
      return [str(v) for v in raw]
    return []

  def _parse_type_definitions(self, types: Dict[str, dict]) -> Dict[str, TypeDefinition]:
    parsed: Dict[str, TypeDefinition] = {}
    for name, data in (types or {}).items():
      try:
        parsed[name] = TypeDefinition.from_dict(name, data)
      except ValueError as e:
        print(f"Warning: Skipping type '{name}': {e}")
    return parsed

  def _parse_message_groups(self, messages: dict) -> Dict[str, Dict[str, MessageInfo]]:
    """Parse message groups (commands/states/configs) into MessageInfo objects."""
    parsed_groups = {}
    allowed_groups = ["commands", "states", "configs"]
    for group_name, group_messages in messages.items():
      if group_name not in allowed_groups:
        raise ValueError(f"Unknown message group '{group_name}', expected one of {allowed_groups}")
      parsed_groups[group_name] = self._parse_messages(group_messages,group_name)
    return parsed_groups

  def _parse_messages(self, messages_dict: dict,group:str) -> Dict[str, MessageInfo]:
    """Parse messages dict and return MessageInfo objects with validation."""
    parsed = {}
    for msg_name, msg_data in (messages_dict or {}).items():
      try:
        parsed[msg_name] = MessageInfo.from_dict(msg_name, msg_data,group)
        if group == "commands" :
          parsed[msg_name].permission_write = True
          parsed[msg_name].permission_read = True
        if group == "states" :
          parsed[msg_name].permission_write = False
          parsed[msg_name].permission_read = True
      except ValueError as e:
        print(f"Warning: {e}")
    return parsed

  def _collect_inherited_messages(self, inherit_list: List[str]) -> Dict[str, Dict[str, MessageInfo]]:
    """Collect messages from type_modules, organized by group (commands/states/configs).
    
    Returns: {group -> {msg_name -> MessageInfo}}
    """
    collected: Dict[str, Dict[str, MessageInfo]] = {}
    for collection_name in inherit_list:
      # Find type_module with matching origin
      for type_mod in self.type_modules:
        if type_mod.origin == collection_name:
          # custom_messages is: {group -> {msg_name -> MessageInfo}}
          # Merge all groups from this collection
          for group_name, messages in type_mod.messages.items():
            if group_name not in collected:
              collected[group_name] = {}
            # Add messages from this collection to the group
            collected[group_name].update(messages)
          break
    return collected

  def _merge_inherited_messages(self, module_messages: Dict[str, Dict[str, MessageInfo]], inherited: Dict[str, Dict[str, MessageInfo]]) -> Dict[str, Dict[str, MessageInfo]]:
    """Merge inherited messages into module message groups.
    
    Both inherited and module_messages have format: {group -> {msg_name -> MessageInfo}}
    Returns: {group -> {msg_name -> MessageInfo}}
    """
    merged: Dict[str, Dict[str, MessageInfo]] = {}
    # First, add inherited messages by group
    for group_name, messages in inherited.items():
      if group_name not in merged:
        merged[group_name] = {}
      merged[group_name].update(messages)
    # Then, add/override with module-specific messages
    for group_name, module_msgs in module_messages.items():
      if group_name not in merged:
        merged[group_name] = {}
      merged[group_name].update(module_msgs)
    return merged


__all__ = [
  "ConfigLoader",
  "HardwareInfo",
  "MessageInfo",
  "ModuleConfig",
  "TypeModule",
  "TypeDefinition",
  "TypeField",
]
