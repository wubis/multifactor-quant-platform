import argparse

from multifactor_platform.ingestion.point_in_time import import_packet
from multifactor_platform.jobs.common import print_json


def main():
    parser = argparse.ArgumentParser(description='Validate and archive a normalized point-in-time data packet.')
    parser.add_argument('directory', help='Directory containing manifest.json and the three contract CSV files')
    parser.add_argument('--output-dir', default='data/processed/research')
    parser.add_argument("--example", action="store_true", help="Create a fictitious test packet in a new directory first")
    args = parser.parse_args()
    if args.example:
        from multifactor_platform.ingestion.point_in_time_sample import write_example
        write_example(args.directory)
    print_json(import_packet(args.directory, args.output_dir))


if __name__ == '__main__':
    main()
