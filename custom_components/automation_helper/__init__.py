"""Automation Helper integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Any, Callable

import voluptuous as vol
import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

LOGGER = logging.getLogger(__name__)

DOMAIN = "automation_helper"
SERVICE_GENERATE_AUTOMATION = "generate_automation"
SERVICE_GENERATE_PACKAGE = "generate_package"


@dataclass
class AutomationDefinition:
    """Container for an automation definition."""

    alias: str
    description: str | None
    mode: str
    trigger: list[dict[str, Any]]
    condition: list[dict[str, Any]] | None
    action: list[dict[str, Any]]

    def to_yaml(self) -> str:
        """Return a YAML representation of the automation."""
        automation: dict[str, Any] = {
            "alias": self.alias,
            "mode": self.mode,
            "trigger": self.trigger or [],
            "action": self.action or [],
        }

        if self.description:
            automation["description"] = self.description

        if self.condition:
            automation["condition"] = self.condition

        return yaml.safe_dump(
            automation,
            sort_keys=False,
            indent=2,
            default_flow_style=False,
            allow_unicode=True,
        )


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("alias"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("mode", default="single"): cv.string,
        vol.Optional("filename"): cv.string,
        vol.Optional("overwrite", default=False): cv.boolean,
        vol.Required("trigger"): vol.All(cv.ensure_list, [cv.SCRIPT_SCHEMA]),
        vol.Optional("condition"): vol.All(cv.ensure_list, [cv.SCRIPT_SCHEMA]),
        vol.Required("action"): vol.All(cv.ensure_list, [cv.SCRIPT_SCHEMA]),
    }
)


PACKAGE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("overwrite", default=False): cv.boolean,
        vol.Optional("include_example", default=True): cv.boolean,
        vol.Optional("include_scripts", default=True): cv.boolean,
        vol.Optional("include_scenes", default=False): cv.boolean,
        vol.Optional("include_readme", default=True): cv.boolean,
        vol.Optional("blueprint_domain", default="automation"): vol.In({"automation", "script"}),
        vol.Optional("include_blueprint", default=False): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Automation Helper integration."""

    await _async_register_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Automation Helper from a config entry."""

    await _async_register_service(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Automation Helper config entry."""

    if hass.services.has_service(DOMAIN, SERVICE_GENERATE_AUTOMATION):
        hass.services.async_remove(DOMAIN, SERVICE_GENERATE_AUTOMATION)
    if hass.services.has_service(DOMAIN, SERVICE_GENERATE_PACKAGE):
        hass.services.async_remove(DOMAIN, SERVICE_GENERATE_PACKAGE)
    return True


async def _async_register_service(hass: HomeAssistant) -> None:
    """Register the automation generation service if needed."""

    if hass.services.has_service(DOMAIN, SERVICE_GENERATE_AUTOMATION):
        return

    async def handle_generate(call: ServiceCall) -> None:
        definition = AutomationDefinition(
            alias=call.data["alias"],
            description=call.data.get("description"),
            mode=call.data["mode"],
            trigger=call.data["trigger"],
            condition=call.data.get("condition"),
            action=call.data["action"],
        )

        filename = call.data.get("filename") or slugify(definition.alias) + ".yaml"
        overwrite = call.data["overwrite"]

        output_dir = Path(hass.config.path("automation_helper"))
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / filename

        if output_file.exists() and not overwrite:
            raise HomeAssistantError(
                f"Automation Helper refused to overwrite existing file: {output_file}"
            )

        yaml_data = definition.to_yaml()

        LOGGER.debug("Writing automation to %s", output_file)
        await _async_write_file(hass, output_file, yaml_data, overwrite)

        LOGGER.info("Automation saved to %s", output_file)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_AUTOMATION,
        handle_generate,
        schema=SERVICE_SCHEMA,
    )

    async def handle_generate_package(call: ServiceCall) -> None:
        package_name = call.data["name"].strip()
        description = call.data.get("description")
        overwrite = call.data["overwrite"]
        include_example = call.data["include_example"]
        include_scripts = call.data["include_scripts"]
        include_scenes = call.data["include_scenes"]
        include_readme = call.data["include_readme"]
        include_blueprint = call.data["include_blueprint"]
        blueprint_domain = call.data["blueprint_domain"]

        if not package_name:
            raise HomeAssistantError("Package name cannot be empty")

        slug = slugify(package_name)
        human_title = humanize(package_name)

        packages_root = Path(hass.config.path("packages"))
        packages_root.mkdir(parents=True, exist_ok=True)

        package_dir = packages_root / slug

        if package_dir.exists() and not overwrite and any(package_dir.iterdir()):
            raise HomeAssistantError(
                f"Automation Helper refused to overwrite non-empty package directory: {package_dir}"
            )

        package_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, Callable[[], str]] = {
            "automations.yaml": lambda: build_automation_package_yaml(
                human_title, description, include_example
            )
        }

        if include_scripts:
            files["scripts.yaml"] = lambda: build_scripts_package_yaml(human_title, include_example)

        if include_scenes:
            files["scenes.yaml"] = lambda: build_scenes_package_yaml(human_title, include_example)

        if include_readme:
            files["README.md"] = lambda: build_package_readme(
                human_title, description, include_scripts, include_scenes, include_blueprint
            )

        if include_blueprint:
            blueprint_dir = package_dir / "blueprints" / blueprint_domain
            blueprint_dir.mkdir(parents=True, exist_ok=True)
            blueprint_path = blueprint_dir / f"{slug}.yaml"

            blueprint_content = build_blueprint_yaml(human_title, description, blueprint_domain)
            await _async_write_file(hass, blueprint_path, blueprint_content, overwrite)

        for relative_path, builder in files.items():
            output_path = package_dir / relative_path
            content = builder()
            await _async_write_file(hass, output_path, content, overwrite)

        LOGGER.info("Package scaffolding created at %s", package_dir)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_PACKAGE,
        handle_generate_package,
        schema=PACKAGE_SERVICE_SCHEMA,
    )


def slugify(value: str) -> str:
    """Convert an arbitrary string to a filesystem-friendly slug."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_\- ]", "", value)
    value = re.sub(r"[\s\-]+", "_", value)
    return value or "automation"


def humanize(value: str) -> str:
    """Return a human-friendly representation of a slug or identifier."""
    cleaned = re.sub(r"[_\-]+", " ", value).strip()
    return cleaned.title() if cleaned else "Automation"


async def _async_write_file(
    hass: HomeAssistant, path: Path, content: str, overwrite: bool
) -> None:
    """Write text to a file in the executor, guarding against unwanted overwrites."""

    def _write() -> None:
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    try:
        await hass.async_add_executor_job(_write)
    except FileExistsError as err:
        raise HomeAssistantError(f"Automation Helper refused to overwrite {err.args[0]}") from err


def build_automation_package_yaml(
    name: str, description: str | None, include_example: bool
) -> str:
    """Create the default package automation YAML content."""

    header = f"# Automations for the {name} package\n"
    body: dict[str, Any] = {"automation": []}

    if include_example:
        body["automation"].append(
            {
                "alias": f"{name} – example",
                "description": description
                or "Replace the trigger and actions with your real automation logic.",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "binary_sensor.example",
                        "to": "on",
                    }
                ],
                "condition": [],
                "action": [
                    {
                        "service": "logbook.log",
                        "data": {
                            "name": name,
                            "message": "Replace this with useful actions.",
                        },
                    }
                ],
                "mode": "single",
            }
        )

    yaml_body = yaml.safe_dump(
        body,
        sort_keys=False,
        indent=2,
        default_flow_style=False,
        allow_unicode=True,
    )
    return header + yaml_body


def build_scripts_package_yaml(name: str, include_example: bool) -> str:
    """Create a stub scripts.yaml for the package."""

    header = f"# Scripts for the {name} package\n"
    body: dict[str, Any] = {"script": {}}

    if include_example:
        body["script"][slugify(f"{name} helper")] = {
            "alias": f"{name} helper",
            "sequence": [
                {
                    "service": "logbook.log",
                    "data": {
                        "name": name,
                        "message": "Replace this script with your real sequence.",
                    },
                }
            ],
        }

    yaml_body = yaml.safe_dump(
        body,
        sort_keys=False,
        indent=2,
        default_flow_style=False,
        allow_unicode=True,
    )
    return header + yaml_body


def build_scenes_package_yaml(name: str, include_example: bool) -> str:
    """Create a stub scenes.yaml for the package."""

    header = f"# Scenes for the {name} package\n"
    body: dict[str, Any] = {"scene": []}

    if include_example:
        body["scene"].append(
            {
                "name": f"{name} scene",
                "icon": "mdi:palette",
                "entities": {
                    "light.example": {
                        "state": "on",
                        "brightness": 200,
                    }
                },
            }
        )

    yaml_body = yaml.safe_dump(
        body,
        sort_keys=False,
        indent=2,
        default_flow_style=False,
        allow_unicode=True,
    )
    return header + yaml_body


def build_package_readme(
    name: str,
    description: str | None,
    include_scripts: bool,
    include_scenes: bool,
    include_blueprint: bool,
) -> str:
    """Create a README.md describing the package contents."""

    lines = [f"# {name} package", ""]

    if description:
        lines.append(description)
    else:
        lines.append("Describe the goal of this automation package.")

    lines.extend(["", "## Contents", "", "- `automations.yaml`"])

    if include_scripts:
        lines.append("- `scripts.yaml`")

    if include_scenes:
        lines.append("- `scenes.yaml`")

    if include_blueprint:
        lines.append("- `blueprints/` automation or script blueprint")

    lines.extend(
        [
            "",
            "## Getting started",
            "",
            "1. Adjust the example entries to match your devices.",
            "2. Load the package by enabling `packages:` in `configuration.yaml`.",
            "3. Restart Home Assistant and verify the automations appear as expected.",
        ]
    )

    return "\n".join(lines) + "\n"


def build_blueprint_yaml(
    name: str, description: str | None, domain: str
) -> str:
    """Create a stub blueprint YAML file."""

    blueprint = {
        "blueprint": {
            "name": f"{name} helper blueprint",
            "description": description
            or "Adapt this blueprint to create reusable automations or scripts.",
            "domain": domain,
            "input": {
                "target_entity": {
                    "name": "Target entity",
                    "description": "Entity that should receive the action.",
                    "selector": {"entity": {}},
                }
            },
            "source_url": "https://github.com/404GamerNotFound/ha_automation_helper",
        },
    }

    if domain == "automation":
        blueprint["blueprint"]["trigger"] = [
            {
                "platform": "state",
                "entity_id": "!input target_entity",
                "to": "on",
            }
        ]
        blueprint["blueprint"]["action"] = [
            {
                "service": "logbook.log",
                "data": {
                    "name": name,
                    "message": "Blueprint triggered – replace with useful actions.",
                },
            }
        ]
    else:
        blueprint["blueprint"]["sequence"] = [
            {
                "service": "logbook.log",
                "data": {
                    "name": name,
                    "message": "Blueprint executed – replace with useful steps.",
                },
            }
        ]

    yaml_body = yaml.safe_dump(
        blueprint,
        sort_keys=False,
        indent=2,
        default_flow_style=False,
        allow_unicode=True,
    )
    yaml_body = yaml_body.replace("'!input target_entity'", "!input target_entity")
    yaml_body = yaml_body.replace('"!input target_entity"', "!input target_entity")
    return yaml_body
