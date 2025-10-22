# Home Assistant Automation Helper

Automation Helper is a custom [Home Assistant](https://www.home-assistant.io/) integration designed
for users who prefer to maintain their automations as code. The integration exposes a
single service that scaffolds cleanly structured automation YAML files, helping teams keep
consistent formatting, naming and directory layout in larger projects.

This repository is ready to be installed through [HACS](https://hacs.xyz/).

## Features

* **Automation scaffolding service** – generate automation files in a dedicated folder
  using familiar trigger/condition/action dictionaries.
* **Package scaffolding service** – spin up a ready-to-edit Home Assistant package with
  automations, scripts, scenes, and optional blueprint boilerplate.
* **Consistent formatting** – the service outputs tidy YAML (sorted keys disabled, two
  space indentation) to keep code reviews easy.
* **Safe file handling** – files are stored inside `<config>/automation_helper/` and will
  never be overwritten unless explicitly allowed.

## Installation

1. Add this repository to HACS (Custom repositories → Integration).
2. Download and install the **Automation Helper** integration.
3. Restart Home Assistant.
4. (Optional) Add the integration through **Settings → Devices & Services** if you prefer a
   config entry. No options are required—the service is available immediately after restart.

## Usage

### Generate a single automation file

Call the `automation_helper.generate_automation` service from Developer Tools or an automation.
Provide the same dictionaries you would normally place inside `automations.yaml`.

```yaml
service: automation_helper.generate_automation
data:
  alias: "Hallway lights when motion"
  description: "Turns on the hallway lights for five minutes when motion is detected"
  mode: queued
  trigger:
    - platform: state
      entity_id: binary_sensor.hallway_motion
      to: "on"
  action:
    - service: light.turn_on
      target:
        entity_id: light.hallway
    - delay: "00:05:00"
    - service: light.turn_off
      target:
        entity_id: light.hallway
```

A file named `hallway_lights_when_motion.yaml` will be created inside the
`automation_helper` folder of your Home Assistant configuration directory. To overwrite an
existing file, set `overwrite: true`.

### Scaffold an entire automation package

Call the `automation_helper.generate_package` service to create a consistent folder under
`<config>/packages/`. The generated files help teams get started faster when structuring a
new area of the home:

```yaml
service: automation_helper.generate_package
data:
  name: hallway_lighting
  description: "Automations and scripts that power the hallway lights"
  include_scripts: true
  include_scenes: true
  include_blueprint: true
  blueprint_domain: automation
```

The service will create a `packages/hallway_lighting/` directory containing
`automations.yaml`, `scripts.yaml`, `README.md`, and optional example content. Provide
`overwrite: true` to replace existing files safely.

## Development

1. Clone the repository into your Home Assistant `custom_components` folder.
2. Adjust the code in `custom_components/automation_helper/` to fit your needs.
3. Run Home Assistant in a development environment and watch the logs for
   `automation_helper` entries.

Contributions and ideas for additional automation utilities are welcome!
