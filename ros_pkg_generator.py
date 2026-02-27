#!/usr/bin/env python3
"""ROS 2 Package Generator for CAN Module Framework.

Generates ROS 2 packages with message definitions from YAML module configs.
- Each ModuleConfig gets a package: <module_name>_msgs
- Each TypeModule gets a package: <type_module>_msgs
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from read_confg_yaml import ModuleConfig, TypeModule, TypeDefinition, TypeField, MessageInfo

from cpp_codegen import ModuleHeaderGenerator


@dataclass
class ROSPackageInfo:
    """Information about a ROS package to generate."""
    name: str
    description: str
    types: Dict[str, "TypeDefinition"]  # custom types to generate as messages
    messages: Dict[str, "MessageInfo"]  # messages to generate
    dependencies: Set[str]  # other ROS packages this depends on
    module_config: Optional["ModuleConfig"] = None  # original module config for main header generation


class ROSMessageGenerator:
    """Generate ROS 2 .msg files from YAML type definitions."""
    
    def __init__(self):
        self.primitive_map = {
            "bool": "bool",
            "uint8": "uint8",
            "int8": "int8",
            "uint16": "uint16",
            "int16": "int16",
            "uint32": "uint32",
            "int32": "int32",
            "uint64": "uint64",
            "int64": "int64",
            "float": "float32",
            "double": "float64",
            "char": "char",
            "string": "string",
        }
        # C++ standard types for code generation
        self.cpp_primitive_map = {
            "bool": "bool",
            "uint8": "std::uint8_t",
            "int8": "std::int8_t",
            "uint16": "std::uint16_t",
            "int16": "std::int16_t",
            "uint32": "std::uint32_t",
            "int32": "std::int32_t",
            "uint64": "std::uint64_t",
            "int64": "std::int64_t",
            "float": "float",
            "double": "double",
            "char": "char",
            "string": "std::string",
        }
    
    def generate_msg_for_type(self, type_def: "TypeDefinition", package_name: str, all_types: Optional[Dict[str, "TypeDefinition"]] = None, type_registry: Optional[Dict[str, str]] = None) -> str:
        """Generate ROS .msg content from TypeDefinition.
        
        Args:
            type_def: Type definition to convert
            package_name: Name of the package (for custom type references)
            all_types: All type definitions (for resolving ros_mapping)
            type_registry: Registry mapping type names to package names
            
        Returns:
            Content of the .msg file
        """
        lines = []
        
        # Header comment
        if type_def.description:
            lines.append(f"# {type_def.description}")
        if type_def.readable_name:
            lines.append(f"# {type_def.readable_name}")
        if type_def.ros_mapping:
            lines.append(f"# Note: Consider using {type_def.ros_mapping} instead")
        if lines:
            lines.append("")
        
        if type_def.kind == "enum":
            # ROS doesn't have enums, use constants
            lines.append("# Enum values (use constants)")
            for value, description in type_def.values.items():
                # Sanitize constant name: must be uppercase and valid identifier
                const_name = self._sanitize_constant_name(description)
                lines.append(f"uint8 {const_name}={value}")
                if description != const_name:
                    lines[-1] += f"  # {description}"
            lines.append("")
            lines.append("# Current value")
            lines.append("uint8 value")
            
        elif type_def.kind == "struct":
            # Generate fields
            for field_name, field in type_def.fields.items():
                msg_type = self._map_type_to_ros(field.var_type, package_name, all_types, type_registry)
                
                # Handle arrays
                if field.array_size:
                    msg_line = f"{msg_type}[{field.array_size}] {field_name}"
                else:
                    msg_line = f"{msg_type} {field_name}"
                
                # Add default value if available
                # if field.default is not None:
                #     msg_line += f" {field.default}"
                
                lines.append(msg_line)
                
                # Add field comment
                if field.description:
                    lines[-1] += f"  # {field.description}"
        
        return "\n".join(lines) + "\n"
    
    def generate_msg_for_message(self, msg_info: "MessageInfo", package_name: str, all_types: Optional[Dict[str, "TypeDefinition"]] = None, type_registry: Optional[Dict[str, str]] = None) -> str:
        """Generate ROS .msg content from MessageInfo.
        
        Args:
            msg_info: Message info to convert
            package_name: Name of the package (for custom type references)
            all_types: All type definitions (for resolving ros_mapping)
            type_registry: Registry mapping type names to package names
            
        Returns:
            Content of the .msg file
        """
        lines = []
        
        # Header comment
        if msg_info.description:
            lines.append(f"# {msg_info.description}")
        if msg_info.readable_name:
            lines.append(f"# {msg_info.readable_name}")
        if msg_info.ros_mapping:
            lines.append(f"# Note: Consider using {msg_info.ros_mapping} instead")
        if lines:
            lines.append("")
        
        # Add standard ROS header for timestamp and frame_id
        lines.append("std_msgs/Header header")
        lines.append("")
        
        # Map the type
        msg_type = self._map_type_to_ros(msg_info.var_type, package_name, all_types, type_registry)
        
        # Handle arrays
        if msg_info.array_size:
            msg_line = f"{msg_type}[{msg_info.array_size}] data"
        else:
            msg_line = f"{msg_type} data"
        
        lines.append(msg_line)
        
        # Add metadata as comments
        if msg_info.units:
            lines.append(f"# Units: {msg_info.units}")
        if msg_info.range:
            lines.append(f"# Range: {msg_info.range}")
        
        return "\n".join(lines) + "\n"
    
    def _map_type_to_ros(self, var_type: str, package_name: str, type_defs: Optional[Dict[str, "TypeDefinition"]] = None, type_registry: Optional[Dict[str, str]] = None) -> str:
        """Map YAML type to ROS message type.
        
        Args:
            var_type: Type name from YAML
            package_name: Current package name
            type_defs: Optional dictionary of type definitions to check for ros_mapping
            type_registry: Optional registry mapping type names to package names
            
        Returns:
            ROS message type string
        """
        # Check if it's a primitive type
        if var_type in self.primitive_map:
            return self.primitive_map[var_type]
        
        # Check if there's a ros_mapping for this type
        if type_defs and var_type in type_defs:
            type_def = type_defs[var_type]
            if type_def.ros_mapping:
                return type_def.ros_mapping
        
        # Check if the type is in another package (via type_registry)
        if type_registry and var_type in type_registry:
            actual_package = type_registry[var_type]
            return f"{actual_package}/{self._to_camel_case(var_type)}"
        
        # Otherwise, it's a custom type - reference from same package
        # Convert snake_case to CamelCase
        return f"{package_name}/{self._to_camel_case(var_type)}"
    
    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to CamelCase."""
        components = snake_str.split('_')
        return ''.join(x.title() for x in components)
    
    def _sanitize_constant_name(self, name: str) -> str:
        """Sanitize a string to be a valid ROS constant name.
        
        ROS constants must match pattern: ^[A-Z]([A-Z0-9_]?[A-Z0-9]+)*$
        - Must start with uppercase letter
        - Can contain A-Z, 0-9, underscore
        - Must be uppercase
        
        Args:
            name: Input string to sanitize
            
        Returns:
            Valid ROS constant name
        """
        import re
        
        # Convert to uppercase
        name = name.upper()
        
        # Replace spaces and hyphens with underscores
        name = name.replace(' ', '_').replace('-', '_')
        
        # Remove any characters that aren't A-Z, 0-9, or underscore
        name = re.sub(r'[^A-Z0-9_]', '', name)
        
        # Ensure it starts with a letter
        if name and not name[0].isalpha():
            name = 'VALUE_' + name
        
        # Remove consecutive underscores
        name = re.sub(r'_+', '_', name)
        
        # Remove trailing underscores
        name = name.rstrip('_')
        
        # If empty after sanitization, use a default
        if not name:
            name = 'UNKNOWN'
        
        return name


class ROSPackageGenerator:
    """Generate complete ROS 2 packages from module configs."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.msg_generator = ROSMessageGenerator()
        self.cpp_generator = ModuleHeaderGenerator(global_namespace="mcan")
        self.type_registry: Dict[str, str] = {}  # {type_name: package_name}
        self.generated_packages: Set[str] = set()  # Track actually generated package names
        self.ros_packages: Set[str] = set()  # Packages in ROS environment
        self.previously_generated: Set[str] = set()  # Packages in generated/ directory
        self.known_packages: Set[str] = set()  # Union of all known packages

        self.generic_dependency_packages = set()  # Track packages that are dependencies but not generated (e.g. ROS standard messages)

        # self.generic_dependency_packages.add("yaml-cpp")  # For parameter loading in plugin
        self.generic_dependencies = set()  
        # self.generic_dependencies.add("yaml-cpp")  # For primitive type wrappers
    
    def _discover_ros_packages(self) -> None:
        """Discover packages available in ROS environment."""
        try:
            from ament_index_python.packages import get_packages_with_prefixes
            ros_pkgs = get_packages_with_prefixes()
            self.ros_packages = set(ros_pkgs.keys())            
        except ImportError:
            # ament_index not available (not in ROS env)
            print("  Warning: ament_index_python not available, ROS package discovery disabled")
        except Exception as e:
            print(f"  Warning: ROS package discovery failed: {e}")
    
    def _discover_generated_packages(self) -> None:
        """Discover packages in generated/ directory."""
        if not self.output_dir.exists():
            return
        for package_xml in self.output_dir.rglob("package.xml"):
            pkg_name = package_xml.parent.name
            self.previously_generated.add(pkg_name)        
    
    def _should_generate_package(self, package_name: str, force: bool, force_all: bool) -> tuple:
        """
        Determine if package should be generated.
        
        Returns:
            (should_generate: bool, reason: str)
        """
        # Check generated directory
        if package_name in self.previously_generated:
            if force or force_all:
                return (True, "regenerating (force)")
            else:
                return (False, "already generated")
        
        # Check ROS environment
        if package_name in self.ros_packages:
            if force_all:
                return (True, "force-all (will create duplicate!)")
            else:
                return (False, "exists in ROS environment")
        
        
        # New package
        return (True, "new package")

    
    def generate_packages_from_loader(self, loader: "ConfigLoader", gen_dummy: bool = False, force: bool = False, force_all: bool = False) -> List[Path]:
        """Generate ROS packages from ConfigLoader.
        
        Args:
            loader: ConfigLoader instance with loaded modules
            gen_dummy: Generate dummy packages without system dependencies
            force: Regenerate packages in generated/ directory
            force_all: Regenerate ALL packages (may create duplicates)
            
        Returns:
            List of paths to generated packages
        """
        # Discovery phase
        self._discover_ros_packages()
        self._discover_generated_packages()
        self.known_packages = self.ros_packages | self.previously_generated
        
        generated_packages = []
        skipped_packages = []
        
        # First pass: Build type registry (map type names to packages)
        for type_module in loader.get_type_modules():
            package_name = f"{type_module.origin}_msgs"
            for type_name in type_module.custom_types.keys():
                self.type_registry[type_name] = package_name
        
        for module in loader.get_modules():
            package_name = f"{module.hardware.name}_msgs"
            for type_name in module.custom_types.keys():
                self.type_registry[type_name] = package_name
        
        # Second pass: Generate packages for TypeModules
        for type_module in loader.get_type_modules():
            package_name = f"{type_module.origin}_msgs"
            
            should_gen, reason = self._should_generate_package(package_name, force, force_all)
            
            if not should_gen:
                skipped_packages.append((package_name, reason))
                print(f"  Skipping {package_name} ({reason})")
                self.known_packages.add(package_name)  # Track as known
                continue
            
            print(f"  Generating {package_name} ({reason})")
            pkg_path = self._generate_type_module_package(type_module, loader, gen_dummy)
            if pkg_path:
                generated_packages.append(pkg_path)
                self.generated_packages.add(package_name)
                self.known_packages.add(package_name)
        
        # Third pass: Generate packages for ModuleConfigs
        for module in loader.get_modules():
            package_name = f"{module.hardware.name}_msgs"
            
            should_gen, reason = self._should_generate_package(package_name, force, force_all)
            
            if not should_gen:
                skipped_packages.append((package_name, reason))
                print(f"  Skipping {package_name} ({reason})")
                self.known_packages.add(package_name)  # Track as known
                continue
            
            print(f"  Generating {package_name} ({reason})")
            pkg_path = self._generate_module_package(module, loader, gen_dummy)
            if pkg_path:
                generated_packages.append(pkg_path)
                self.generated_packages.add(package_name)
                self.known_packages.add(package_name)
        
        # Summary
        if skipped_packages:
            print(f"\nSkipped {len(skipped_packages)} package(s)")
  
        
        return generated_packages

    def _generate_type_module_package(self, type_module: "TypeModule", loader: "ConfigLoader",gen_dummy:bool=False) -> Optional[Path]:
        """Generate ROS package for a TypeModule."""
        
        package_name = f"{type_module.origin}_msgs"
        package_dir = self.output_dir / package_name
        
        # Collect all messages and types
        all_messages = {}
        for group_name, messages in type_module.messages.items():
            all_messages.update(messages)
        
        # Collect all types from loader for type resolution
        all_types = {}
        for tm in loader.get_type_modules():
            all_types.update(tm.custom_types)
        for mod in loader.get_modules():
            all_types.update(mod.custom_types)
        
        # Collect dependencies from ros_mapping fields
        dependencies = self.generic_dependency_packages.copy()  # Start with generic dependencies
        for type_def in type_module.custom_types.values():
            if type_def.ros_mapping and '/' in type_def.ros_mapping:
                pkg_name = type_def.ros_mapping.split('/')[0]
                if pkg_name != package_name:
                    dependencies.add(pkg_name)
        for msg_info in all_messages.values():
            if msg_info.ros_mapping and '/' in msg_info.ros_mapping:
                pkg_name = msg_info.ros_mapping.split('/')[0]
                if pkg_name != package_name:
                    dependencies.add(pkg_name)
        
        pkg_info = ROSPackageInfo(
            name=package_name,
            description=f"Messages for {type_module.origin} type module",
            types=type_module.custom_types,
            messages=all_messages,
            dependencies=dependencies,
            module_config=None  # Type modules don't have full module config
        )
        
        return self._generate_package(pkg_info, package_dir, all_types,gen_dummy)
    
    def _generate_module_package(self, module: "ModuleConfig", loader: "ConfigLoader",gen_dummy:bool=False) -> Optional[Path]:
        """Generate ROS package for a ModuleConfig."""
        package_name = f"{module.hardware.name}_msgs"
        package_dir = self.output_dir / package_name
        
        # Collect all messages from all groups
        all_messages = {}
        for group_name, messages in module.messages.items():
            all_messages.update(messages)
        
        # Collect all types from loader for type resolution
        all_types = {}
        for tm in loader.get_type_modules():
            all_types.update(tm.custom_types)
        for mod in loader.get_modules():
            all_types.update(mod.custom_types)
            all_messages.update(messages)
        
        # Collect dependencies based on includes
        dependencies = self.generic_dependency_packages.copy()  # Start with generic dependencies
        if not gen_dummy:
          dependencies.add("mc_plugin_driver")  # Depend on the main driver package for module plugin interface
          dependencies.add("mc_can_driver")  # For ROS plugin system
  
        for include in module.includes:
            dep_pkg = f"{include}_msgs"
            # Only add if this package is known (in ROS, generated, or being generated)
            if dep_pkg in self.known_packages:
                dependencies.add(dep_pkg)
        
        # Add dependencies from ros_mapping fields
        for type_def in all_types.values():
            if type_def.ros_mapping and '/' in type_def.ros_mapping:
                pkg_name = type_def.ros_mapping.split('/')[0]
                if pkg_name != package_name:
                    dependencies.add(pkg_name)
        
        pkg_info = ROSPackageInfo(
            name=package_name,
            description=f"Messages for {module.hardware.name} module",
            types=module.custom_types,
            messages=all_messages,
            dependencies=dependencies,
            module_config=module  # Store module config for main header generation
        )
        
        return self._generate_package(pkg_info, package_dir, all_types,gen_dummy)
    
    def _generate_package(self, pkg_info: ROSPackageInfo, package_dir: Path, all_types: Optional[Dict[str, "TypeDefinition"]] = None, gen_dummy:bool=False) -> Path:
        """Generate a complete ROS 2 package.
        
        Args:
            pkg_info: Package information
            package_dir: Directory to create package in
            all_types: All type definitions from all modules (for type resolution)
            package_dir: Directory to create package in
            
        Returns:
            Path to generated package
        """
        # Create directory structure
        package_dir.mkdir(parents=True, exist_ok=True)
        msg_dir = package_dir / "msg"
        msg_dir.mkdir(exist_ok=True)
        
        # Generate message files for custom types
        for type_name, type_def in pkg_info.types.items():
            # Skip if has ros_mapping (use standard ROS message instead)
            if type_def.ros_mapping:
                continue
            msg_content = self.msg_generator.generate_msg_for_type(type_def, pkg_info.name, all_types, self.type_registry)
            msg_file = msg_dir / f"{self.msg_generator._to_camel_case(type_name)}.msg"
            msg_file.write_text(msg_content)
        
        # Generate message files for messages
        for msg_name, msg_info in pkg_info.messages.items():
            # Skip if has ros_mapping (use standard ROS message instead)
            if msg_info.ros_mapping:
                continue
            msg_content = self.msg_generator.generate_msg_for_message(msg_info, pkg_info.name, all_types, self.type_registry)
            msg_file = msg_dir / f"{self.msg_generator._to_camel_case(msg_name)}.msg"
            msg_file.write_text(msg_content)
        
        # Generate C++ type headers using cpp_codegen
        self._generate_cpp_headers(pkg_info, package_dir)
        
        # Generate CAN encoders/decoders (header-only with struct)
        self._generate_conversions_struct(pkg_info, package_dir, all_types)

        # generate module plugin for ROS 2 node factory
        if not gen_dummy:
          self._generate_module_plugin(pkg_info, package_dir)

        # Generate package.xml
        
        self._generate_package_xml(pkg_info, package_dir)
        
        # Generate CMakeLists.txt
        self._generate_cmakelists(pkg_info, package_dir, msg_dir,gen_dummy)

        if not gen_dummy:
          self._genrate_plugin_xml(pkg_info, package_dir)
        
        return package_dir
    
    def _generate_package_xml(self, pkg_info: ROSPackageInfo, package_dir: Path):
        """Generate package.xml file."""
        content = f"""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{pkg_info.name}</name>
  <version>0.1.0</version>
  <description>{pkg_info.description}</description>
  <maintainer email="user@todo.todo">Your Name</maintainer>
  <license>TODO</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <buildtool_depend>rosidl_default_generators</buildtool_depend>

  <depend>std_msgs</depend>
  <depend>pluginlib</depend>
"""
        
        # Add dependencies
        for dep in sorted(pkg_info.dependencies):
            content += f"  <depend>{dep}</depend>\n"
        

        content += """
  <exec_depend>rosidl_default_runtime</exec_depend>

  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
"""
        
        (package_dir / "package.xml").write_text(content)
    
    def _generate_cpp_headers(self, pkg_info: ROSPackageInfo, package_dir: Path):
        """Generate C++ type headers using cpp_codegen for the package.
        
        Args:
            pkg_info: Package information
            package_dir: Package directory path
        """
        
        # Create include directory structure: include/<package_name>/
        include_dir = package_dir / "include" / pkg_info.name
        include_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract package name without _msgs suffix
        base_name = pkg_info.name.replace("_msgs", "")
        
        # Collect includes (dependencies without _msgs suffix, excluding ROS packages)
        includes = []
        for dep in sorted(pkg_info.dependencies):
            if dep.endswith("_msgs") and dep in self.generated_packages:
                includes.append(dep.replace("_msgs", ""))
        
        # Generate C++ types header using cpp_codegen
        cpp_content = self.cpp_generator.generate_types_header(
            module_name=base_name,
            custom_types=pkg_info.types,
            includes=includes,
            comment=f"Auto-generated types for {pkg_info.name} ROS package",
            ros_package_mode=True  # Use ROS package-style includes
        )
        
        # Write to include directory
        header_file = include_dir / f"{base_name}_types.hpp"
        header_file.write_text(cpp_content)
        
        # Generate main module header with messages and hardware info
        # Only if we have a complete module config (not just types)
        if pkg_info.module_config:
          main_header_file = include_dir / f"{base_name}.hpp"
          self.cpp_generator.write_module_main_header(
              module=pkg_info.module_config,
              output_path=main_header_file,
              use_ros_include=True  # Use ROS package-style includes
          )
      
        
    
    def _generate_conversions_struct(self, pkg_info: ROSPackageInfo, package_dir: Path, all_types: Optional[Dict[str, "TypeDefinition"]]):
        """Generate CAN encoder/decoder conversion functions as static struct members.
        
        Args:
            pkg_info: Package information
            package_dir: Package directory path
            all_types: All type definitions from all modules
        """
        include_dir = package_dir / "include" / pkg_info.name
        include_dir.mkdir(parents=True, exist_ok=True)
        
        conversions_file = include_dir / "conversions.hpp"
        
        # Generate header content
        lines = []
        lines.append("// Auto-generated CAN frame encoder/decoder for ROS messages")
        lines.append("//")
        lines.append("// DO NOT EDIT MANUALLY")
        lines.append("//")
        lines.append("")
        lines.append("#pragma once")
        lines.append("")
        lines.append("#include <rclcpp/rclcpp.hpp>")
        lines.append("#include <std_msgs/msg/u_int8.hpp>")
        lines.append("#include <std_msgs/msg/u_int16.hpp>")
        lines.append("#include <std_msgs/msg/u_int32.hpp>")
        lines.append("#include <std_msgs/msg/u_int64.hpp>")
        lines.append("#include <std_msgs/msg/int8.hpp>")
        lines.append("#include <std_msgs/msg/int16.hpp>")
        lines.append("#include <std_msgs/msg/int32.hpp>")
        lines.append("#include <std_msgs/msg/int64.hpp>")
        lines.append("#include <std_msgs/msg/float32.hpp>")
        lines.append("#include <std_msgs/msg/float64.hpp>")
        lines.append("#include <std_msgs/msg/bool.hpp>")
        lines.append("")
        
        # Include ROS message headers
        lines.append("// ROS message includes")
        for type_name, type_def in pkg_info.types.items():
            if type_def.ros_mapping:
                # Include the ROS standard message header instead
                if '/' in type_def.ros_mapping:
                    pkg_name = type_def.ros_mapping.split('/')[0]
                    msg_name = type_def.ros_mapping.split('/')[1]
                    lines.append(f"#include <{pkg_name}/msg/{self._to_snake_case(msg_name)}.hpp>")
                continue
            msg_name = self.msg_generator._to_camel_case(type_name)
            lines.append(f"#include <{pkg_info.name}/msg/{self._to_snake_case(msg_name)}.hpp>")
        
        for msg_name, msg_info in pkg_info.messages.items():
            if msg_info.ros_mapping:
                # Include the ROS standard message header instead
                if '/' in msg_info.ros_mapping:
                    pkg_name = msg_info.ros_mapping.split('/')[0]
                    msg_name_ros = msg_info.ros_mapping.split('/')[1]
                    lines.append(f"#include <{pkg_name}/msg/{self._to_snake_case(msg_name_ros)}.hpp>")
                continue
            msg_name_camel = self.msg_generator._to_camel_case(msg_name)
            lines.append(f"#include <{pkg_info.name}/msg/{self._to_snake_case(msg_name_camel)}.hpp>")
        
        lines.append("")
        
        # Include C++ type headers
        lines.append("// C++ type includes")
        base_name = pkg_info.name.replace("_msgs", "")
        lines.append(f"#include <{pkg_info.name}/{base_name}_types.hpp>")
        
        # Include main module header if it exists (for message structs)
        if pkg_info.module_config:
            lines.append(f"#include <{pkg_info.name}/{base_name}.hpp>")
        lines.append("")
        
        # Include conversions from dependency packages
        if pkg_info.dependencies:
            lines.append("// Dependency conversions")
            for dep in sorted(pkg_info.dependencies):
                if dep.endswith("_msgs") and dep in self.generated_packages:
                    lines.append(f"#include <{dep}/conversions.hpp>")
            lines.append("")
        
        # Namespace
        lines.append(f"namespace {pkg_info.name} {{")
        lines.append("")
        
        # Extract namespace for C++ types
        cpp_namespace = f"mcan::{base_name}"
        
        # Create conversion struct
        lines.append("/**")
        lines.append(" * Message conversion utilities for CAN frames and ROS messages.")
        lines.append(" * All methods are static inline for use as template parameters.")
        lines.append(" *")
        lines.append(" * Four conversion types:")
        lines.append(" * 1. mcan_encode_val_to_ros() - Primitive values to std_msgs wrappers")
        lines.append(" * 2. mcan_decode_type_to_ros() - C++ custom types to ROS type messages")
        lines.append(" * 3. mcan_decode_message_to_ros() - Module messages to ROS messages (with header)")
        lines.append(" * 4. mcan_encode_ros_to_message() - ROS messages to module messages")
        lines.append(" */")
        lines.append("struct Conversions {")
        lines.append("")
        
        # 1. Generate primitive value to ROS wrapper helpers
        lines.append("  // ========== Primitive Value to ROS Wrapper ==========")
        lines.append("")
        primitive_wrappers = {
            "uint8": "std_msgs::msg::UInt8",
            "uint16": "std_msgs::msg::UInt16",
            "uint32": "std_msgs::msg::UInt32",
            "uint64": "std_msgs::msg::UInt64",
            "int8": "std_msgs::msg::Int8",
            "int16": "std_msgs::msg::Int16",
            "int32": "std_msgs::msg::Int32",
            "int64": "std_msgs::msg::Int64",
            "float": "std_msgs::msg::Float32",
            "double": "std_msgs::msg::Float64",
            "bool": "std_msgs::msg::Bool",
            
        }
        
        for prim_type, ros_wrapper in primitive_wrappers.items():
            cpp_type = self.msg_generator.cpp_primitive_map.get(prim_type, prim_type)
            lines.append(f"  static inline {ros_wrapper} mcan_encode_val_to_ros(const {cpp_type}& val) {{")
            lines.append(f"    {ros_wrapper} msg;")
            lines.append(f"    msg.data = val;")
            lines.append(f"    return msg;")
            lines.append(f"  }}")
            lines.append("")
        
        lines.append("""
  template<float Scale>
  static inline double
  mcan_decode_type_to_ros(const FloatInt16_t<Scale>& val)
  {
    return (double)val;
  }

  static inline double
  mcan_encode_ros_to_type(const double& val)
  {
    return (double)val;
  }
                         """)

        lines.append("  // ========== Custom Type Conversions ==========")
        lines.append("")
        
        # 2. Generate conversions for custom types (type_to_ros)
        for type_name, type_def in pkg_info.types.items():
            msg_name_camel = self.msg_generator._to_camel_case(type_name)
            cpp_type = f"{cpp_namespace}::{msg_name_camel}_t"
            
            # Check if this type has ros_mapping - use ROS standard message
            if type_def.ros_mapping:
                if '/' in type_def.ros_mapping:
                    pkg_name = type_def.ros_mapping.split('/')[0]
                    msg_name = type_def.ros_mapping.split('/')[1]
                    ros_type = f"{pkg_name}::msg::{msg_name}"
                else:
                    ros_type = type_def.ros_mapping
            else:
                ros_type = f"msg::{msg_name_camel}"
            
            func_suffix = self._to_snake_case(msg_name_camel)
            
            # Decode: C++ type → ROS type message (inline implementation)
            lines.append(f"  /**")
            lines.append(f"   * Convert C++ custom type to ROS type message")
            lines.append(f"   * @param val C++ type instance")
            lines.append(f"   * @return ROS type message")
            if type_def.ros_mapping:
                lines.append(f"   * Direct field mapping to {type_def.ros_mapping}")
            lines.append(f"   */")
            lines.append(f"  static inline {ros_type} mcan_decode_type_to_ros(const {cpp_type}& val) {{")
            
            if type_def.kind == "enum":
                lines.append(f"    {ros_type} msg;")
                lines.append(f"    msg.value = static_cast<uint8_t>(val);")
                lines.append(f"    return msg;")
            elif type_def.kind == "struct":
                lines.append(f"    {ros_type} msg;")
                for field_name, field in type_def.fields.items():
                    field_cpp_type = field.var_type
                    if field_cpp_type in self.msg_generator.primitive_map:
                        lines.append(f"    msg.{field_name} = val.{field_name};")
                    else:
                        field_camel = self.msg_generator._to_camel_case(field_cpp_type)
                        if field_cpp_type in self.type_registry:
                            dep_pkg = self.type_registry[field_cpp_type]
                            lines.append(f"    msg.{field_name} = {dep_pkg}::Conversions::mcan_decode_type_to_ros(val.{field_name});")
                        else:
                            lines.append(f"    msg.{field_name} = mcan_decode_type_to_ros(val.{field_name});")
                lines.append(f"    return msg;")
            lines.append(f"  }}")
            lines.append("")
            
            # Encode: ROS type message → C++ type (inline implementation)
            lines.append(f"  /**")
            lines.append(f"   * Convert ROS type message to C++ custom type")
            lines.append(f"   * @param msg ROS type message")
            lines.append(f"   * @return C++ type instance")
            if type_def.ros_mapping:
                lines.append(f"   * Direct field mapping from {type_def.ros_mapping}")
            lines.append(f"   */")
            lines.append(f"  static inline {cpp_type} mcan_encode_ros_to_type(const {ros_type}& msg) {{")
            
            if type_def.kind == "enum":
                lines.append(f"    return static_cast<{cpp_type}>(msg.value);")
            elif type_def.kind == "struct":
                lines.append(f"    {cpp_type} val;")
                for field_name, field in type_def.fields.items():
                    field_cpp_type = field.var_type
                    if field_cpp_type in self.msg_generator.primitive_map:
                        lines.append(f"    val.{field_name} = msg.{field_name};")
                    else:
                        field_camel = self.msg_generator._to_camel_case(field_cpp_type)
                        if field_cpp_type in self.type_registry:
                            dep_pkg = self.type_registry[field_cpp_type]
                            lines.append(f"    val.{field_name} = {dep_pkg}::Conversions::mcan_encode_ros_to_type(msg.{field_name});")
                        else:
                            lines.append(f"    val.{field_name} = mcan_encode_ros_to_type(msg.{field_name});")
                lines.append(f"    return val;")
            
            lines.append(f"  }}")
            lines.append("")
        
        lines.append("  // ========== Module Message Conversions ==========")
        lines.append("")
        if pkg_info.module_config:
          # 3 & 4. Generate conversions for messages
          # These convert between ROS messages and C++ module message structs
          # (e.g., mcan::motor_hat::commands::SetMotorPosition ↔ msg::SetMotorPosition)
          for msg_name, msg_info in pkg_info.messages.items():
              msg_name_camel = self.msg_generator._to_camel_case(msg_name)
              
              # Check if message has ros_mapping - use ROS standard message
              if msg_info.ros_mapping:
                  if '/' in msg_info.ros_mapping:
                      pkg_name = msg_info.ros_mapping.split('/')[0]
                      msg_name_ros = msg_info.ros_mapping.split('/')[1]
                      ros_type = f"{pkg_name}::msg::{msg_name_ros}"
                  else:
                      ros_type = msg_info.ros_mapping
              else:
                  ros_type = f"msg::{msg_name_camel}"
                            
              # C++ module message struct type (from main module header)
              # e.g., mcan::motor_hat::commands::SetMotorPosition
              cpp_msg_type = f"{cpp_namespace}::{msg_info.group}::{msg_name_camel}"
              
              # Determine the inner value type
              cpp_var_type = msg_info.var_type
              if cpp_var_type in self.msg_generator.primitive_map:
                  cpp_value_type = self.msg_generator.cpp_primitive_map[cpp_var_type]
              else:
                  if cpp_var_type in self.type_registry:
                      pkg = self.type_registry[cpp_var_type]
                      base_pkg = pkg.replace("_msgs", "")
                      cpp_value_type = f"mcan::{base_pkg}::{self.msg_generator._to_camel_case(cpp_var_type)}_t"
                  else:
                      cpp_value_type = f"{cpp_namespace}::{self.msg_generator._to_camel_case(cpp_var_type)}_t"
              
              # 3. Decode: C++ module message struct → ROS message
              lines.append(f"  /**")
              lines.append(f"   * Convert C++ module message struct to ROS message")
              lines.append(f"   * @param msg_struct C++ module message struct (from main header)")
              if msg_info.ros_mapping:
                  lines.append(f"   * @return ROS standard message {msg_info.ros_mapping} (header not initialized)")
              else:
                  lines.append(f"   * @return ROS message with data (header not initialized)")
              lines.append(f"   */")
              lines.append(f"  static inline {ros_type} mcan_decode_message_to_ros(const {cpp_msg_type}& msg_struct) {{")
              lines.append(f"    {ros_type} msg;")
              
              # Extract the value field from the message struct
              if cpp_var_type in self.msg_generator.primitive_map:
                  if msg_info.ros_mapping:
                      # For ros_mapping with primitive, assume direct assignment (rare case)
                      lines.append(f"    // Primitive direct mapping to ROS standard message")
                      lines.append(f"    msg.data = msg_struct.value;")
                  else:
                      lines.append(f"    msg.data = msg_struct.value;")
              else:
                  # Custom type - convert using type conversion
                  type_camel = self.msg_generator._to_camel_case(cpp_var_type)
                  if msg_info.ros_mapping:
                      # For ros_mapping, the cpp_type should map directly (no .data field)
                      if cpp_var_type in self.type_registry:
                          dep_pkg = self.type_registry[cpp_var_type]
                          lines.append(f"    return {dep_pkg}::Conversions::mcan_decode_type_to_ros(msg_struct.value);")
                      else:
                          lines.append(f"    return mcan_decode_type_to_ros(msg_struct.value);")
                  else:
                      if cpp_var_type in self.type_registry:
                          dep_pkg = self.type_registry[cpp_var_type]
                          lines.append(f"    msg.data = {dep_pkg}::Conversions::mcan_decode_type_to_ros(msg_struct.value);")
                      else:
                          lines.append(f"    msg.data = mcan_decode_type_to_ros(msg_struct.value);")
              
              if not (cpp_var_type not in self.msg_generator.primitive_map and msg_info.ros_mapping):
                  lines.append(f"    return msg;")
              lines.append(f"  }}")
              lines.append("")
              
              # 4. Encode: ROS message → C++ module message struct (strips header)
              lines.append(f"  /**")
              if msg_info.ros_mapping:
                  lines.append(f"   * Convert ROS standard message to C++ module message struct")
              else:
                  lines.append(f"   * Convert ROS message to C++ module message struct (extracts data, ignores header)")
              lines.append(f"   * @param msg ROS message instance")
              lines.append(f"   * @return C++ module message struct (from main header)")
              lines.append(f"   */")
              lines.append(f"  static inline {cpp_msg_type} mcan_encode_ros_to_message(const {ros_type}& msg) {{")
              lines.append(f"    {cpp_msg_type} msg_struct;")
              
              # Set the value field in the message struct
              if cpp_var_type in self.msg_generator.primitive_map:
                  if msg_info.ros_mapping:
                      lines.append(f"    // Primitive direct mapping from ROS standard message")
                      lines.append(f"    msg_struct.value = msg.data;")
                  else:
                      lines.append(f"    msg_struct.value = msg.data;")
              else:
                  # Custom type - convert using type conversion
                  type_camel = self.msg_generator._to_camel_case(cpp_var_type)
                  if msg_info.ros_mapping:
                      # For ros_mapping, convert directly (no .data field)
                      if cpp_var_type in self.type_registry:
                          dep_pkg = self.type_registry[cpp_var_type]
                          lines.append(f"    msg_struct.value = {dep_pkg}::Conversions::mcan_encode_ros_to_type(msg);")
                      else:
                          lines.append(f"    msg_struct.value = mcan_encode_ros_to_type(msg);")
                  else:
                      if cpp_var_type in self.type_registry:
                          dep_pkg = self.type_registry[cpp_var_type]
                          lines.append(f"    msg_struct.value = {dep_pkg}::Conversions::mcan_encode_ros_to_type(msg.data);")
                      else:
                          lines.append(f"    msg_struct.value = mcan_encode_ros_to_type(msg.data);")
              
              lines.append(f"    return msg_struct;")
              lines.append(f"  }}")
              lines.append("")
        
        # Close struct
        lines.append("};  // struct Conversions")
        lines.append("")
        lines.append(f"}}  // namespace {pkg_info.name}")
        lines.append("")
        
        conversions_file.write_text("\n".join(lines))
    
    def _to_snake_case(self, camel_str: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def _generate_cmakelists(self, pkg_info: ROSPackageInfo, package_dir: Path, msg_dir: Path,gen_dummy:bool=False):
        """Generate CMakeLists.txt file."""
        # Collect all .msg files
        msg_files = sorted([f.name for f in msg_dir.glob("*.msg")])
        
        content = f"""cmake_minimum_required(VERSION 3.8)
project({pkg_info.name})

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(pluginlib REQUIRED)
"""
        
        # Add dependency finding
        for dep in sorted(pkg_info.dependencies):
            content += f"find_package({dep} REQUIRED)\n"
        
        for dep in sorted(self.generic_dependencies):
            content += f"find_package({dep} REQUIRED)\n"

        
        # Only generate messages if there are .msg files
        if msg_files:
            content += "\nfind_package(rosidl_default_generators REQUIRED)\n"
            content += "\n# Generate messages\n"
            content += "rosidl_generate_interfaces(${PROJECT_NAME}\n"
            
            # Add all message files
            for msg_file in msg_files:
                content += f'  "msg/{msg_file}"\n'
            
            content += "  DEPENDENCIES std_msgs"
            
            # Add dependencies
            for dep in sorted(pkg_info.dependencies):
                content += f" {dep}"
            
            content += "\n)\n\n"
        else:
            # No message files - package only provides conversions for ros_mapping types
            content += "\n# Note: This package has no .msg files (all types use ros_mapping)\n"
            content += "# Package provides conversion utilities only\n\n"
        
        ## Create interface library for C++ headers
        
        # Create an INTERFACE library to export C++ headers to downstream packages
        base_name = pkg_info.name.replace("_msgs", "")
        content += f"\n# Create interface library for C++ type headers\n"
        content += f"add_library({base_name}_cpp_headers INTERFACE)\n"
        content += f"target_include_directories({base_name}_cpp_headers INTERFACE\n"
        content += "  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>\n"
        content += "  $<INSTALL_INTERFACE:include>)\n"
        
        # Add dependencies to the interface library
        if pkg_info.dependencies:
            content += f"ament_target_dependencies({base_name}_cpp_headers INTERFACE"
            for dep in sorted(pkg_info.dependencies):
                if dep.endswith("_msgs"):
                    content += f" {dep}\n"
            content += ")\n"
        
        # Install the interface library
        content += f"install(TARGETS {base_name}_cpp_headers\n"
        content += f"  EXPORT {base_name}_cpp_headersTargets)\n"
        content += f"install(EXPORT {base_name}_cpp_headersTargets\n"
        content += f"  DESTINATION share/${{PROJECT_NAME}}/cmake)\n\n"


        # Add rclcpp dependency for the plugin executable
        content += "find_package(rclcpp REQUIRED)\n\n"

        if  pkg_info.module_config and not gen_dummy:
        
          ## PLUGIN
          # Add plugin executable (temporary - will be converted to plugin later)
          content += "# Module plugin library \n"
          content += f"add_library({base_name}_plugin SHARED  src/{base_name}_plugin.cpp)\n"
          content += f"target_compile_features({base_name}_plugin PUBLIC c_std_99 cxx_std_23)\n"
          content += (f"target_include_directories({base_name}_plugin PUBLIC\n"
                      f"  $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/include>\n"
                      f"  $<INSTALL_INTERFACE:include/${{PROJECT_NAME}}>\n"
                      f")\n")
          content += f"target_link_libraries({base_name}_plugin"
          content += f"  PUBLIC\n"
          content += f"    ${{pluginlib_TARGETS}}\n"
          content += f"    {base_name}_cpp_headers\n"
          content += f"    yaml-cpp\n"
          content += f"    mc_plugin_driver::mc_plugin_driver\n"
          content += f")\n\n"

          content += f"ament_target_dependencies({base_name}_plugin\n"
          content += f"  PUBLIC\n"
          content += f"    rclcpp\n"
          content += f"    pluginlib\n"
          content += f"    yaml-cpp\n"
          # content += f"    {base_name}_cpp_headers\n"
          for dep in sorted(pkg_info.dependencies):
              if dep.endswith("_msgs"):
                  content += f"    {dep}\n"
          content += "\n)\n\n"
          content += f"rosidl_get_typesupport_target(cpp_typesupport_target  ${{PROJECT_NAME}} \"rosidl_typesupport_cpp\")\n"
          content += f"target_link_libraries({base_name}_plugin PUBLIC ${{cpp_typesupport_target}})\n\n"

          # Install plugin library
          content += f"install(TARGETS {base_name}_plugin\n"
          content += "  DESTINATION lib/${PROJECT_NAME})\n\n"

          # Export plugin description file for pluginlib

          content += f"pluginlib_export_plugin_description_file(mc_plugin_driver plugins.xml)\n"

          content += f"install(TARGETS {base_name}_plugin\n"
          content += f"  DESTINATION lib/${{PROJECT_NAME}})\n"
          ## PLUGIN


        content += f"install(\n"
        content += f"DIRECTORY include/\n"
        content += f"DESTINATION include\n)\n"
        
        # Export include directories and dependencies so other packages can find them
        content += "# Export include directories for downstream packages\n"
        content += "ament_export_include_directories(include)\n"
        content += f"ament_export_targets({base_name}_cpp_headersTargets)\n"
        if pkg_info.dependencies:
            content += "ament_export_dependencies("
            for dep in sorted(pkg_info.dependencies):
                content += f"{dep} "
            content += "std_msgs)\n"
        else:
            content += "ament_export_dependencies(std_msgs)\n"
        content += "\n"
        
        content += "ament_package()"
        
        (package_dir / "CMakeLists.txt").write_text(content)

    def _generate_module_plugin(self, pkg_info: ROSPackageInfo, package_dir: Path):
        """Generate a plugin main file with all necessary includes for the module.
        
        Args:
            pkg_info: Package information
            package_dir: Package directory path
        """
        # Create src directory
        src_dir = package_dir / "src"
        src_dir.mkdir(exist_ok=True)

        if not pkg_info.module_config:
            return  # No module config, so no plugin needed
        
        base_name = pkg_info.name.replace("_msgs", "")
        
        lines = []
        lines.append("// Auto-generated plugin main file for ROS 2")
        lines.append("//")
        lines.append("// This will be converted to a plugin implementation")
        lines.append("//")
        lines.append("")
        
        # Include ROS headers
        lines.append("// ROS 2 includes")
        lines.append("#include <rclcpp/rclcpp.hpp>")
        lines.append("")
        
        # Include module type headers
        lines.append("// Module type headers")
        lines.append(f"#include <{pkg_info.name}/{base_name}_types.hpp>")
        
        # Include main module header if it exists (has messages and Hardware_t)
        if pkg_info.module_config:
            lines.append(f"#include <{pkg_info.name}/{base_name}.hpp>")
        lines.append("")
        
        # Include conversions
        lines.append("// Conversion utilities")
        lines.append(f"#include <{pkg_info.name}/conversions.hpp>")
        lines.append("")
        
        # Include all generated ROS messages
        lines.append("// Generated ROS messages")
        for type_name, type_def in pkg_info.types.items():
            if type_def.ros_mapping:
                # Include ROS standard message
                if '/' in type_def.ros_mapping:
                    pkg_name = type_def.ros_mapping.split('/')[0]
                    msg_name = type_def.ros_mapping.split('/')[1]
                    lines.append(f"#include <{pkg_name}/msg/{self._to_snake_case(msg_name)}.hpp>")
            else:
                msg_name = self.msg_generator._to_camel_case(type_name)
                lines.append(f"#include <{pkg_info.name}/msg/{self._to_snake_case(msg_name)}.hpp>")
        
        for msg_name, msg_info in pkg_info.messages.items():
            if msg_info.ros_mapping:
                # Include ROS standard message
                if '/' in msg_info.ros_mapping:
                    pkg_name = msg_info.ros_mapping.split('/')[0]
                    msg_name_ros = msg_info.ros_mapping.split('/')[1]
                    lines.append(f"#include <{pkg_name}/msg/{self._to_snake_case(msg_name_ros)}.hpp>")
            else:
                msg_name_camel = self.msg_generator._to_camel_case(msg_name)
                lines.append(f"#include <{pkg_info.name}/msg/{self._to_snake_case(msg_name_camel)}.hpp>")
        lines.append("")
        
        # Include dependency package conversions
        if pkg_info.dependencies:
            lines.append("// Dependency conversions")
            for dep in sorted(pkg_info.dependencies):
                if dep.endswith("_msgs") and dep in self.generated_packages:
                    lines.append(f"#include <{dep}/conversions.hpp>")
            lines.append("")
        
        # Include plugin driver headers
        lines.append("#include <mc_plugin_driver/mc_plugin_driver.hpp>")
        lines.append("#include <mc_plugin_driver/mc_slave_driver.hpp>")
        lines.append("#include <mc_plugin_driver/mc_param.hpp>")
        lines.append("#include <mc_plugin_driver/mc_plugin_exporter.hpp>")
        lines.append("#include <mc_can_driver/can_linux_driver.hpp>")
        lines.append("")
        lines.append("")
        
        # Generate plugin class
        lines.append("namespace mcan {")
        lines.append(f"class {base_name}_plugin : public McPluginExporterBase {{")
        lines.append("public:")
        lines.append(f"  {base_name}_plugin() : McPluginExporterBase() {{")
        lines.append("  }")
        lines.append("")
        lines.append("  virtual Result<std::shared_ptr<McSlavePluginDriverBase>> create_new_instance(rclcpp::Node &node,")
        lines.append("                                                                               std::shared_ptr<CanBase> can_primary,")
        lines.append("                                                                               std::shared_ptr<CanBase> can_secondary,")
        lines.append("                                                                               const ModuleParams &params) override {")
        lines.append("    auto result =")
        lines.append(f"    mcan::McSlavePluginDriver<mcan::{base_name}::McCanSlaveInterface_t, mcan::{base_name}::Hardware_t, {pkg_info.name}::Conversions>::Make(")
        lines.append("    node, std::move(can_primary), std::move(can_secondary), params);")
        lines.append("")
        lines.append("    if(!result.ok()) {")
        lines.append("      return result.status();")
        lines.append("    }")
        lines.append("    return Result<std::shared_ptr<McSlavePluginDriverBase>>::OK(")
        lines.append("    std::shared_ptr<McSlavePluginDriverBase>(result.valueOrDie()));")
        lines.append("  }")
        lines.append("")
        lines.append("  virtual uint64_t get_plugin_unique_id() const override {")
        lines.append(f"    return mcan::{base_name}::Hardware_t::k_unique_id;")
        lines.append("  };")
        lines.append("};")
        lines.append("")
        lines.append("}; // namespace mcan")
        lines.append("")
        lines.append("#include \"pluginlib/class_list_macros.hpp\"")
        lines.append(f"PLUGINLIB_EXPORT_CLASS(mcan::{base_name}_plugin, mcan::McPluginExporterBase)")
        lines.append("")
        
        # Write to src directory
        plugin_file = src_dir / f"{base_name}_plugin.cpp"
        plugin_file.write_text("\n".join(lines))

    def _genrate_plugin_xml(self, pkg_info: ROSPackageInfo, package_dir: Path):
        """Generate a plugin description XML file for the module.
        
        Args:
            pkg_info: Package information
            package_dir: Package directory path
        """

        if not pkg_info.module_config:
            return  # No module config, so no plugin needed

        base_name = pkg_info.name.replace("_msgs", "")
        content = f"<library path=\"{base_name}_plugin\">\n"
        content += f"  <class name=\"{base_name}_msgs\" type=\"mcan::{base_name}_plugin\" base_class_type=\"mcan::McPluginExporterBase\">\n"
        content += f"    <description>Plugin for {base_name}.{pkg_info.module_config.hardware.description if pkg_info.module_config else "" }</description>\n"
        content += f"  </class>\n"
        content += f"</library>\n"
        (package_dir / "plugins.xml").write_text(content)

def main():
    """Main entry point for ROS package generation."""
    import sys
    import argparse
    from read_confg_yaml import ConfigLoader
    from datetime import datetime
    
    parser = argparse.ArgumentParser(
        description="Generate ROS 2 packages from YAML module configurations"
    )
    parser.add_argument(
        "modules",
        nargs="*",
        help="YAML module files to process (default: example_module_config.yaml)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output directory for generated packages (default: src/generated/ros)"
    )
    parser.add_argument(
        "-i", "--include",
        action="append",
        default=[],
        help="Additional directories to search for includes (default: src/)"
    )
    parser.add_argument(
        "-d", "--dummy",
        action="store_true",
        help="Generate dummy packages that don't require all dependencies (for testing)"
    )
    
    args = parser.parse_args()
    
    root = Path(__file__).parent
    
    # Setup paths
    if args.modules:
      module_files = [Path(f) for f in args.modules]
    else:
      module_files = [root / "basic_module_dummy.yaml"]
      # raise Exception(f"No module files specified. Please provide YAML module configuration files as arguments.\nExample usage:\n  python ros_pkg_generator.py -i src/ src/example_module_config.yaml")
      # example_module_config   basic_module_dummy
    
    include_dirs = [root] + [Path(d) for d in args.include]
    
    if args.output:
      output_dir = Path(args.output)
    else:
      output_dir = root / "generated" / "ros"

    gen_dummy = args.dummy 

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load configurations
    print("Loading configurations...")
    loader = ConfigLoader(include_dirs)
    loader.load_files(module_files)
    
    print(f"Loaded {len(loader.get_modules())} device(s)")
    for mod in loader.get_modules():
      print(f" - {mod.hardware.name}")
      print(f"     Driver ID: 0x{mod.hardware.unique_id:02X}")
      print(f"     Manufacturer: {mod.hardware.vendor}")
      print(f"     Descriptio: {mod.hardware.description}")
      date_str = datetime.fromtimestamp(mod.hardware.date).strftime('%Y-%m-%d')
      print(f"     Version: {mod.hardware.hw_revision}:{mod.hardware.fw_revision} ({date_str})")

    print(f"\n{'='*60}")

    print(f"Loaded {len(loader.get_type_modules())} additional type module(s)")
    for type_mod in loader.get_type_modules():
      print(f" - {type_mod.origin}")
    
    # Generate ROS packages
    print(f"\n{'='*60}")
    print("\nGenerating ROS2 packages...")
    generator = ROSPackageGenerator(output_dir)
    generated = generator.generate_packages_from_loader(loader,gen_dummy)
    print(f"Generated {len(generated)} ROS2 package(s):")
    for pkg_path in generated:
      print(f" - {pkg_path.name}")

    print(f"\nOutput: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
  main()