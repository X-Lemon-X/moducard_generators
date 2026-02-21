from pathlib import Path
import sys
import argparse
from read_confg_yaml import ConfigLoader
from datetime import datetime
from ros_pkg_generator import ROSPackageGenerator
from cpp_codegen import ModuleHeaderGenerator


def main():
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
        help="Generate dummy packages that won't required the main system dependencies (default: False)"
    )

    parser.add_argument(
        "-r", "--ros",
        action="store_true",
        help="Generate ros packages (default: False)"
    )

    parser.add_argument(
        "-f", "--firmware",
        action="store_true",
        help="Generate firmware packages (default: False)"
    )    
    args = parser.parse_args()
    root = Path(__file__).parent
    
    # Setup paths
    if args.modules:
      module_files = [Path(f) for f in args.modules]
    else:
      module_files = [root / "basic_module_dummy.yaml"]
      # raise Exception(f"No module files specified. Please provide YAML module configuration files as arguments.\nExample usage:\n  python ros_pkg_generator.py -i src/ src/example_module_config.yaml")
    
    if not args.ros and not args.firmware:
      print("No generation target specified. Use --ros / -r and/or --firmware / -f to specify what to generate.")
      sys.exit(1)
      return

    include_dirs = [root, root / "modules" ]  + [Path(d) for d in args.include]
    
    if args.output:
      output_dir = Path(args.output)
    else:
      output_dir = root / ".." / ".." / "generated" 

    gen_dummy = args.dummy 
    output_dir_ros = output_dir / "ros"
    output_dir_firmware = output_dir / "firmware"

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.ros:
      output_dir_ros.mkdir(parents=True, exist_ok=True)
    if args.firmware:
      output_dir_firmware.mkdir(parents=True, exist_ok=True)
    
    print(f"{'='*60}")
    print(f"Include directories:\n")
    for inc_dir in include_dirs:
      print(f" - {inc_dir}")
    print(f"{'='*60}")

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
    if args.ros:
      print(f"\n{'='*60}")
      print("\nGenerating ROS2 packages...")
      generator = ROSPackageGenerator(output_dir)
      generated = generator.generate_packages_from_loader(loader,gen_dummy)
      print(f"Generated {len(generated)} ROS2 package(s):")
      for pkg_path in generated:
        print(f" - {pkg_path.name}")

    # Generate firmware packages
    if args.firmware:
      print(f"\n{'='*60}")
      print("\nGenerating firmware files...")
      generator = ModuleHeaderGenerator('mcan')
      for module in loader.get_modules():
        out1, out2 = generator.write_module_header(module, output_dir_firmware)
        print(f" - {module.hardware.name} : {out1} | {out2}")

      for type_module in loader.get_type_modules():
        out = generator.write_type_module_header(type_module, output_dir_firmware)
        print(f" - {type_module.origin} : {out}")


    print(f"\nOutput: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
  main()