"""
Script for managing the iceberg catalog.
"""

import argparse

from utils.askii_art import print_ascii_art
from utils.iceberg_management import drop_iceberg_table, drop_namespace


def delete_table() -> None:
    namespace_to_delete = input("What is the name of the namespace?").strip()
    table_to_delete = input("What is the name of the table you want to delete?").strip()
    if not namespace_to_delete or not table_to_delete:
        print("Namespace and table name cannot be empty.")
        return

    drop_iceberg_table(namespace=namespace_to_delete, table_name=table_to_delete)


def delete_namespace() -> None:
    namespace_to_delete = input("What is the name of the namespace you want to delete?").strip()
    if not namespace_to_delete:
        print("Namespace name cannot be empty.")
        return

    drop_namespace(namespace_to_delete)


def main(args: argparse.Namespace) -> None:
    print_ascii_art()
    print("Iceberg Catalog Management:")

    if args:
        if args.command == "delete" and args.target == "namespace":
            print(f"Dropping namespace {args.namespace.strip()}...")
            drop_namespace(args.namespace.strip(), purge=not args.no_purge)
        elif args.command == "delete" and args.target == "table":
            print(f"Dropping table {args.table.strip()} in namespace {args.namespace.strip()}...")
            drop_iceberg_table(
                namespace=args.namespace.strip(),
                table_name=args.table.strip(),
                purge=not args.no_purge,
            )
        else:
            raise ValueError("Invalid command or target.")
        exit(0)
    else:
        print("Please select the action you want to perform:")
        print("1. Delete Namespace")
        print("2. Drop Tables")

        action_input = input("Action to perform (1 or 2): ").strip()

        if action_input == "1":
            delete_namespace()
        elif action_input == "2":
            delete_table()
        else:
            raise ValueError("Invalid action selected. Please choose 1 or 2.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Iceberg Catalog Management CLI")
    parser.add_argument("command", help="Action to perform (e.g., delete)")
    parser.add_argument("target", help="Target of the command (e.g., namespace, table)")
    parser.add_argument("-n", "--namespace", type=str, help="Targeted namespace")
    parser.add_argument("-t", "--table", type=str, help="Targeted table")
    parser.add_argument(
        "--no-purge", action="store_true", help="Skip deletion of blob storage data"
    )
    args = parser.parse_args()

    main(args)
