from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING


from config_helpers import is_base_type

if TYPE_CHECKING:
    from read_confg_yaml import ModuleConfig, HardwareInfo, TypeDefinition, TypeField, MessageInfo

class ModuleHeaderGenerator:
  """Generate C++ headers for TypeModule (type-only files).
  
  Creates headers with nested namespaces:
  - Global namespace (user-specified)
  - Module-specific namespace (matching module name)
  - Contains only custom type definitions (structs and enums)
  """

  def __init__(self, global_namespace: Optional[str] = None) -> None:
      """Initialize generator with global namespace.
      
      Args:
          global_namespace: Top-level namespace to wrap all types (e.g., "mcan")
      """
      self.global_namespace = global_namespace
      self.primitive_map: Dict[str, str] = {
          "bool": "bool",
          "uint8": "uint8_t",
          "int8": "int8_t",
          "uint16": "uint16_t",
          "int16": "int16_t",
          "uint32": "uint32_t",
          "int32": "int32_t",
          "uint64": "uint64_t",
          "int64": "int64_t",
          "float": "float",
          "double": "double",
          "char": "char",
      }

      self.super_types = {
        "float_int16": "FloatInt16_t"
      }

  def write_type_module_header(self, type_module: "TypeModule", output_path: Path | str) -> Path:
        """Generate and write TypeModule header to file.
        
        Args:
            type_module: TypeModule instance to generate header for
            output_path: Path where to write the header file
            
        Returns:
            Path object of the written file
        """
        path = Path(output_path)
        path = path / f"{type_module.origin}_types.hpp"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self._generate_type_module_header(type_module)
        path.write_text(content, encoding="utf-8")
        return path

  def _generate_type_module_header(self, type_module: "TypeModule") -> str:
      """Generate C++ header content for a TypeModule.
      
      Args:
          type_module: TypeModule instance with custom_types to generate
          
      Returns:
          Complete C++ header file content as string
      """
      return self.generate_types_header(
          module_name=type_module.origin,
          custom_types=type_module.custom_types,
          includes=type_module.includes,
          comment=f"Auto-generated from {type_module.origin} type module"
      )
  

  def generate_types_header(self, module_name: str, custom_types: Dict[str, "TypeDefinition"], includes: List[str], comment: str, ros_package_mode: bool = False) -> str:
      """Generate C++ types header content (shared by TypeModule and ModuleConfig).
      
      Args:
          module_name: Name of the module/origin for namespace
          custom_types: Dictionary of TypeDefinition objects
          includes: List of include file names
          comment: Header comment text
          ros_package_mode: If True, generate ROS package-style includes with <package_msgs/...>
          
      Returns:
          Complete C++ header file content as string
      """
      lines: List[str] = []
      
      # Header
      lines.append(f"// {comment}")
      lines.append("//")
      lines.append("// DO NOT EDIT MANUALLY")
      lines.append("//")
      lines.append("")
      lines.append("#pragma once")
      lines.append("")
      lines.append("#include <cstdint>")
      lines.append("#include <string>")
      lines.append("#include <cstddef>")
      # mc_firmware/super_types.hpp is always in the same directory
      if ros_package_mode:
          lines.append("#include \"mc_plugin_base/mc_firmware/super_types.hpp\"")
      else:
        lines.append("#include \"mc_firmware/super_types.hpp\"")
      lines.append("")
      
      # Include headers for referenced includes
      if includes:
          for inc in includes:
              if ros_package_mode:
                  # ROS package style: <package_msgs/module_types.hpp>
                  lines.append(f'#include <{inc}_msgs/{inc}_types.hpp>')
              else:
                  # Regular style: "module_types.hpp"
                  lines.append(f'#include "{inc}_types.hpp"')
          lines.append("")
      
      # Open global namespace
      if self.global_namespace:
          lines.append(f"namespace {self.global_namespace} {{")
          lines.append("")
      
      # Open module namespace
      module_ns = self._sanitize_namespace(module_name)
      lines.append(f"namespace {module_ns} {{")
      lines.append("")
      
      # Add using namespace declarations for includes
      if includes:
          lines.append("// Using declarations for included namespaces")
          for inc in includes:
              inc_ns = self._sanitize_namespace(inc)
              if self.global_namespace:
                  lines.append(f"using namespace {self.global_namespace}::{inc_ns};")
              else:
                  lines.append(f"using namespace {inc_ns};")
          lines.append("")
      
      # Forward declarations
      if custom_types:
          lines.append("// Forward declarations")
          for type_name, type_def in custom_types.items():
              cpp_name = self._to_cpp_type_name(type_name)
              if type_def.kind == "enum":
                  lines.append(f"enum class {cpp_name} : std::uint8_t;")
              elif type_def.kind == "struct":
                  lines.append(f"struct {cpp_name};")
          lines.append("")
      
      # Type definitions
      if custom_types:
          lines.append("// Type definitions")
          lines.append("")
          for type_name, type_def in custom_types.items():
              cpp_name = self._to_cpp_type_name(type_name)
              if type_def.kind == "enum":
                  lines.extend(self._generate_enum(cpp_name, type_def))
              elif type_def.kind == "struct":
                  lines.extend(self._generate_struct(cpp_name, type_def))
              lines.append("")
      
      # Close namespaces
      lines.append(f"}}  // namespace {module_ns}")
      if self.global_namespace:
          lines.append("")
          lines.append(f"}}  // namespace {self.global_namespace}")
      
      return "\n".join(lines)
  
  def _sanitize_namespace(self, name: str) -> str:
      """Convert module name to valid C++ namespace identifier."""
      # Replace non-alphanumeric characters with underscores
      ns = re.sub(r"[^a-zA-Z0-9_]", "_", name)
      
      # Handle empty string
      if not ns:
          return "types"
      
      # Cannot start with digit
      if ns[0].isdigit():
          ns = "ns_" + ns
      
      return ns
  
  def _to_cpp_type_name(self, type_name: str) -> str:
      """Convert type name to C++ type name (PascalCase with _t suffix)."""
      # Split by non-alphanumeric characters
      parts = re.split(r"[^a-zA-Z0-9]+", type_name)
      # Capitalize each part
      cpp_name = "".join(part.capitalize() for part in parts if part)
      
      # Add _t suffix if not already present
      if not cpp_name.lower().endswith("_t"):
          cpp_name += "_t"
      
      return cpp_name
  
  def _to_cpp_field_name(self, field_name: str) -> str:
      """Convert field name to valid C++ identifier."""
      return re.sub(r"[^a-zA-Z0-9_]", "_", field_name)
  
  def _resolve_cpp_type(self, var_type: str, array_size: Optional[int], scale:Optional[str]) -> Tuple[str, Optional[int]]:
      """Resolve C++ type from var_type string.
      
      Returns:
          Tuple of (cpp_type_string, array_size)
      """
      # Check if it's a primitive type
      if var_type in self.primitive_map:
          return (self.primitive_map[var_type], array_size)
      
      if var_type in self.super_types:
          if scale is  None:
            raise ValueError(f"Type '{var_type}' requires a scale factor.")
          return (f"{self.super_types[var_type]}<{str(scale)}f>", array_size)

      # Custom type - convert to C++ type name
      return (self._to_cpp_type_name(var_type), array_size)
  
  def _generate_enum(self, cpp_name: str, type_def: "TypeDefinition") -> List[str]:
      """Generate C++ enum class definition."""
      lines: List[str] = []
      
      # Add doxygen comment if description exists
      if type_def.description or type_def.readable_name:
          lines.append("/**")
          if type_def.readable_name:
              lines.append(f" * @brief {type_def.readable_name}")
          if type_def.description:
              lines.append(f" * {type_def.description}")
          lines.append(" */")
      
      lines.append(f"enum class {cpp_name} : std::uint8_t {{")
      
      # Sort enum values by key (numeric value)
      try:
          sorted_values = sorted(type_def.values.items(), key=lambda x: int(x[0]))
      except (ValueError, TypeError):
          # If keys aren't numeric, keep original order
          sorted_values = list(type_def.values.items())
      
      for value_key, value_desc in sorted_values:
          enum_label = self._to_enum_label(value_desc)
          lines.append(f"    {enum_label} = {value_key},")
      
      lines.append("};")
      
      return lines
  
  def _generate_struct(self, cpp_name: str, type_def: "TypeDefinition") -> List[str]:
      """Generate C++ struct definition."""
      lines: List[str] = []
      
      # Add doxygen comment if description exists
      if type_def.description or type_def.readable_name:
          lines.append("/**")
          if type_def.readable_name:
              lines.append(f" * @brief {type_def.readable_name}")
          if type_def.description:
              lines.append(f" * {type_def.description}")
          lines.append(" */")
      
      lines.append(f"struct {cpp_name} {{")
      
      # Generate fields
      for field_name, field_def in type_def.fields.items():
          cpp_field_name = self._to_cpp_field_name(field_name)
          cpp_type, array_size = self._resolve_cpp_type(field_def.var_type, field_def.array_size, field_def.arg)
          
          # Add field documentation
          lines.append("")
          lines.append("    /**")
          if field_def.description:
              lines.append(f"     * @brief {field_def.description}")
          lines.append(f"     * @type {cpp_type}{'[' + str(array_size) + ']' if array_size else ''}")
          if field_def.units:
              lines.append(f"     * @units {field_def.units}")
          if field_def.default is not None:
              lines.append(f"     * @default {field_def.default}")
          if field_def.range:
              lines.append(f"     * @range [{field_def.range[0]}, {field_def.range[1]}]")
          lines.append("     */")
          
          default_value = ""
          if field_def.default is not None:
            default_value = f" = {field_def.default}"

          # Generate field declaration
          if array_size:
              lines.append(f"    {cpp_type} {cpp_field_name}[{array_size}]{default_value};")
          else:
              lines.append(f"    {cpp_type} {cpp_field_name}{default_value};")
      
      lines.append("};")
      
      return lines
  
  def _to_enum_label(self, label: str) -> str:
      """Convert enum value description to C++ enum label (UPPER_CASE)."""
      # Replace non-alphanumeric with underscores and convert to uppercase
      label = re.sub(r"\W+", "_", label).upper()
      
      # Handle empty or invalid labels
      if not label or label[0].isdigit():
          return "VALUE_" + label
      
      return label
    
  def write_module_header(self, module: "ModuleConfig", output_path: Path | str) -> List[Path]:
      """Generate both types header and main module header for ModuleConfig.
      
      Generates two files:
      1. {module_name}_types.hpp - custom type definitions
      2. {module_name}.hpp - messages, Hardware_t, and McCanSlaveInterface_t
      
      Args:
          module: ModuleConfig instance to generate headers for
          output_path: Base path for output (will generate two files)
          
      Returns:
          Path to the main module header file
      """
      output_path = Path(output_path)
      module_name = module.hardware.name
      
      # Generate types header first
      types_path = output_path / f"{module_name}_types.hpp"
      self.write_module_types_header(module, types_path)
      
      # Generate main module header
      main_path = output_path /  f"{module_name}.hpp"
      self.write_module_main_header(module, main_path)
      
      return types_path, main_path
  
  def _generate_cmake_library(self,  include_dirs: List[Path], source_files: List[Path]) :
    
    pass    

  def write_module_types_header(self, module: "ModuleConfig", output_path: Path) -> None:
      """Generate types-only header for ModuleConfig."""
      module_name = module.hardware.name
      
      content = self.generate_types_header(
          module_name=module_name,
          custom_types=module.custom_types,
          includes=module.includes,
          comment=f"Auto-generated types for {module_name} module"
      )
      
      # Write file
      output_path.parent.mkdir(parents=True, exist_ok=True)
      output_path.write_text(content, encoding="utf-8")
  
  def write_module_main_header(self, module: "ModuleConfig", output_path: Path, use_ros_include:bool=False) -> None:
      """Generate main module header with messages, Hardware_t, and McCanSlaveInterface_t."""
      lines: List[str] = []
      module_name = module.hardware.name
      
      # Header
      lines.append(f"// Auto-generated header for {module_name} module")
      lines.append("// Do not edit manually")
      lines.append("")
      lines.append("#pragma once")
      lines.append("")
      lines.append("#include <cstdint>")
      lines.append("#include <string>")
      lines.append("#include <cstddef>")
      lines.append("#include <tuple>")
      
      if use_ros_include:
        lines.append("#include \"mc_plugin_base/mc_firmware/super_types.hpp\"")
      else:
        lines.append("#include \"mc_firmware/super_types.hpp\"")
      lines.append("")
      
      # Include types header
      if use_ros_include:
          lines.append(f'#include <{module_name}_msgs/{module_name}_types.hpp>')
      else:
        lines.append(f'#include "{module_name}_types.hpp"')

      lines.append("")
      
      # Open global namespace
      if self.global_namespace:
          lines.append(f"namespace {self.global_namespace} {{")
          lines.append("")
      
      # Open module namespace
      module_ns = self._sanitize_namespace(module_name)
      lines.append(f"namespace {module_ns} {{")
      lines.append("")
      
      # Generate Hardware_t struct
      lines.extend(self._generate_hardware_struct(module.hardware))
      lines.append("")
      
      # Generate message namespaces (commands, states, configs)
      lines.append("// Message definitions")
      lines.append("")
      
      can_id_counter = 0x10  # Start from 0x10 for messages without explicit IDs
      
      for group in ["commands", "states", "configs"]:
          if group in module.messages and module.messages[group]:
              lines.append(f"namespace {group} {{")
              lines.append("")
              
              for msg_name, msg_info in module.messages[group].items():
                  lines.extend(self._generate_message_struct(msg_name, msg_info, group, can_id_counter))
                  lines.append("")
                  if msg_info.can_id is None:
                      can_id_counter += 1
              
              lines.append(f"}}  // namespace {group}")
              lines.append("")
      
      # Generate McCanSlaveInterface_t class
      lines.extend(self._generate_slave_interface(module.messages,use_ros_include))
      
      # Close namespaces
      lines.append(f"}}  // namespace {module_ns}")
      if self.global_namespace:
          lines.append("")
          lines.append(f"}}  // namespace {self.global_namespace}")
      
      # Write file
      output_path.parent.mkdir(parents=True, exist_ok=True)
      output_path.write_text("\n".join(lines), encoding="utf-8")
  
  def _generate_hardware_struct(self, hardware: "HardwareInfo") -> List[str]:
      """Generate Hardware_t struct."""
      lines: List[str] = []
      
      lines.append("// Hardware information")
      lines.append("struct Hardware_t {")
      lines.append(f"    static constexpr const char* k_name = \"{hardware.name}\";")
      lines.append(f"    static constexpr std::uint32_t k_time_stamp = {hardware.date};")
      lines.append(f"    static constexpr std::uint32_t k_hw_revision = {hardware.hw_revision};")
      lines.append(f"    static constexpr std::uint32_t k_fw_revision = {hardware.fw_revision};")
      
      # Format unique_id as hex
      try:
          if isinstance(hardware.unique_id, str):
              uid = hardware.unique_id.strip()
              if uid.startswith("0x") or uid.startswith("0X"):
                  uid_hex = uid
              else:
                  uid_hex = hex(int(uid, 16))
          else:
              uid_hex = hex(int(hardware.unique_id))
      except:
          uid_hex = "0x0"
      
      lines.append(f"    static constexpr std::uint64_t k_unique_id = {uid_hex};")
      lines.append(f"    static constexpr const char* k_description = \"{hardware.description}\";")
      lines.append("};")
      
      return lines
  
  def _generate_message_struct(self, msg_name: str, msg_info: "MessageInfo", group: str, default_id: int) -> List[str]:
      """Generate message struct definition."""
      lines: List[str] = []
      
      # Determine CAN ID
      if msg_info.can_id is not None:
          try:
              can_id = int(msg_info.can_id)
          except:
              can_id = default_id
      else:
          can_id = default_id
      
      # Resolve C++ type
      cpp_type, array_size = self._resolve_cpp_type(msg_info.var_type, msg_info.array_size, msg_info.arg)
      
      # Struct name (PascalCase)
      struct_name = self._to_message_struct_name(msg_name)
      
      # Add doxygen documentation
      lines.append("/**")
      if msg_info.readable_name:
          lines.append(f" * @brief {msg_info.readable_name}")
      if msg_info.description:
          lines.append(f" * @details {msg_info.description}")
      if msg_info.units:
          lines.append(f" * @units {msg_info.units}")
      if msg_info.default is not None:
          lines.append(f" * @default {msg_info.default}")
      if msg_info.range:
          lines.append(f" * @range [{msg_info.range[0]}, {msg_info.range[1]}]")
      lines.append(f" * @permission {'rw' if msg_info.permission_read and msg_info.permission_write else 'r' if msg_info.permission_read else 'w'}")
      lines.append(" */")
      
      # Struct definition
      lines.append(f"struct {struct_name} {{")
      lines.append(f"    using Type = {cpp_type}{'[' + str(array_size) + ']' if array_size else ''};")
      lines.append(f"    static constexpr const char* k_name = \"{msg_name}\";")
      lines.append(f"    static constexpr const char* k_group = \"{group}\";")
      lines.append(f"    static constexpr std::uint32_t k_base_address = 0x{can_id:03X};")
      lines.append(f"    static constexpr bool k_allow_read = {str(msg_info.permission_read).lower()};")
      lines.append(f"    static constexpr bool k_allow_write = {str(msg_info.permission_write).lower()};")

      lines.append("")

      msg_default_value = ""
      if msg_info.default is not None:
        msg_default_value =  f" = {{{msg_info.default}}}"

      if array_size:
          lines.append(f"    {cpp_type} value[{array_size}]{msg_default_value};")
      else:
          lines.append(f"    {cpp_type} value{msg_default_value};")
      
      lines.append("};")
      
      return lines
  
  def _generate_slave_interface(self, messages: Dict[str, Dict[str, "MessageInfo"]],use_ros_include=False) -> List[str]:
      """Generate McCanSlaveInterface_t class."""
      lines: List[str] = []
      
      lines.append("// CAN MC Slave Interface")
      lines.append("class McCanSlaveInterface_t {")
      lines.append("public:")
      
      # Collect all messages and their namespaces
      all_messages: List[Tuple[str, str, str, "MessageInfo"]] = []  # (group, msg_name, field_name, msg_info)
      
      for group in ["commands", "states", "configs"]:
          if group in messages:
              for msg_name, msg_info in messages[group].items():
                  if msg_info.can_id is None:  # Skip messages with explicit CAN IDs
                      field_name = self._to_cpp_field_name(msg_name)
                      all_messages.append((group, msg_name, field_name, msg_info))
      
      # Generate member variables
      for group, msg_name, field_name, msg_info in all_messages:
          struct_name = self._to_message_struct_name(msg_name)
          lines.append(f"    {group}::{struct_name} {field_name};")
      
      lines.append("")
      
      # Generate callback declarations for writable messages
      writable_messages = [(g, mn, fn, mi) for g, mn, fn, mi in all_messages if mi.permission_write]
      
      if writable_messages and not use_ros_include:
          lines.append("    // Write callbacks")
          for group, msg_name, field_name, msg_info in writable_messages:
              struct_name = self._to_message_struct_name(msg_name)
              lines.append(f"    void callback_write_{field_name}({group}::{struct_name}& variable);")
          lines.append("")
      
      # Generate get_write_callbacks()
      if not use_ros_include:
        if writable_messages:
            lines.append("    auto get_write_callbacks() {")
            lines.append("        return std::make_tuple(")
            for i, (group, msg_name, field_name, msg_info) in enumerate(writable_messages):
                comma = "," if i < len(writable_messages) - 1 else ""
                lines.append(f"            std::make_pair(&McCanSlaveInterface_t::callback_write_{field_name}, &McCanSlaveInterface_t::{field_name}){comma}")
            lines.append("        );")
            lines.append("    }")
            lines.append("")
      else:
        if writable_messages:
            lines.append("    auto get_write_variables() {")
            lines.append("        return std::make_tuple(")
            for i, (group, msg_name, field_name, msg_info) in enumerate(writable_messages):
                comma = "," if i < len(writable_messages) - 1 else ""
                lines.append(f"            &McCanSlaveInterface_t::{field_name}{comma}")
            lines.append("        );")
            lines.append("    }")
            lines.append("")

      # Generate get_read_variables()
      readable_messages = [(g, mn, fn, mi) for g, mn, fn, mi in all_messages if mi.permission_read]
      
      if readable_messages:
          lines.append("    auto get_read_variables() {")
          lines.append("        return std::make_tuple(")
          for i, (group, msg_name, field_name, msg_info) in enumerate(readable_messages):
              comma = "," if i < len(readable_messages) - 1 else ""
              lines.append(f"            &McCanSlaveInterface_t::{field_name}{comma}")
          lines.append("        );")
          lines.append("    }")
          lines.append("")
      
      # Generate get_state_variables()
      state_messages = [(g, mn, fn, mi) for g, mn, fn, mi in all_messages if g == "states"]
      
      if state_messages:
          lines.append("    auto get_state_variables() {")
          lines.append("        return std::make_tuple(")
          for i, (group, msg_name, field_name, msg_info) in enumerate(state_messages):
              comma = "," if i < len(state_messages) - 1 else ""
              lines.append(f"            &McCanSlaveInterface_t::{field_name}{comma}")
          lines.append("        );")
          lines.append("    }")
          lines.append("")
      
      # Generate get_command_variables()
      command_messages = [(g, mn, fn, mi) for g, mn, fn, mi in all_messages if g == "commands"]
      
      if command_messages:
          lines.append("    auto get_command_variables() {")
          lines.append("        return std::make_tuple(")
          for i, (group, msg_name, field_name, msg_info) in enumerate(command_messages):
              comma = "," if i < len(command_messages) - 1 else ""
              lines.append(f"            &McCanSlaveInterface_t::{field_name}{comma}")
          lines.append("        );")
          lines.append("    }")
          lines.append("")
      
      # Generate get_config_variables()
      config_messages = [(g, mn, fn, mi) for g, mn, fn, mi in all_messages if g == "configs"]
      
      if config_messages:
          lines.append("    auto get_config_variables() {")
          lines.append("        return std::make_tuple(")
          for i, (group, msg_name, field_name, msg_info) in enumerate(config_messages):
              comma = "," if i < len(config_messages) - 1 else ""
              lines.append(f"            &McCanSlaveInterface_t::{field_name}{comma}")
          lines.append("        );")
          lines.append("    }")
      
      lines.append("};")
      
      

      return lines
  
  def _to_message_struct_name(self, msg_name: str) -> str:
      """Convert message name to struct name (PascalCase)."""
      parts = re.split(r"[^a-zA-Z0-9]+", msg_name)
      return "".join(part.capitalize() for part in parts if part)
  
  

__all__ = [ "TypeModuleHeaderGenerator"]
