from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from datetime import datetime
from secrets import token_hex

REQUIRED_KEYS = (
  "APP_SECRET_KEY",
  "TOKEN_ENCRYPTION_KEY",
  "JWT_SECRET_KEY",
)


def generate_values() -> dict[str, str]:
  return {
    "TOKEN_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    "APP_SECRET_KEY": token_hex(32),
    "JWT_SECRET_KEY": token_hex(32),
  }


def render_env(values: dict[str, str]) -> str:
  return "\n".join(f"{key}={values[key]}" for key in REQUIRED_KEYS) + "\n"


def create_env_file(temp_dir: Path, values: dict[str, str]) -> Path:
  temp_dir.mkdir(parents=True, exist_ok=True)

  timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
  env_path = temp_dir / f"generated-env-{timestamp}.env"
  counter = 1

  while env_path.exists():
    env_path = temp_dir / f"generated-env-{timestamp}-{counter}.env"
    counter += 1

  env_path.write_text(render_env(values), encoding="utf-8")
  return env_path


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Generate fresh values for required environment keys.",
  )
  parser.add_argument(
    "--output-dir",
    default=None,
    help="Optional directory where the new env file should be created.",
  )
  return parser.parse_args()


def main() -> None:
  args = parse_args()
  values = generate_values()
  default_output_dir = Path(__file__).resolve().parent
  output_dir = Path(args.output_dir) if args.output_dir else default_output_dir
  env_path = create_env_file(output_dir, values)
  print(f"Created {env_path}")


if __name__ == "__main__":
  main()
