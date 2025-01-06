#!/usr/bin/env python3

import sys


def generate_email(full_name):
    # List of common suffixes to ignore
    suffixes = ["Jr.", "Sr.", "III", "IV", "V"]

    parts = full_name.split()

    # If the last chunk is a known suffix, remove it
    if parts[-1] in suffixes:
        parts = parts[:-1]

    # First name is the first element
    first_name = parts[0]
    # Last name is now the last element
    last_name = parts[-1]

    # Construct the email address
    email = f"{first_name[0].lower()}{last_name.lower()}@jlsautomation.com"
    return email


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py \"Full Name\"")
        sys.exit(1)

    # Combine all arguments into a single name (in case there are spaces in the name)
    full_name = " ".join(sys.argv[1:])
    email_address = generate_email(full_name)
    print(email_address)
