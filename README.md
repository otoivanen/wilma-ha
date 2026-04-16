# Wilma Home Assistant Integration

A custom Home Assistant integration that fetches upcoming exams from the [Wilma](https://www.visma.com/finland/wilma/) school portal and exposes them as sensors.

## Features

- One sensor per child showing upcoming exam count
- Exam details available as sensor attributes (date, topic, subject, teacher)
- Fires `wilma_new_exam` event when a new exam appears — use for Telegram notifications
- Configurable poll interval
- Children are auto-discovered after login — no manual ID lookup needed

## Installation via HACS

1. Add this repository as a custom repository in HACS (category: Integration)
2. Install **Wilma** from HACS
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for **Wilma**
5. Enter your Wilma URL, username and password — children are discovered automatically

## Configuration

All configuration is done through the UI. No changes to `configuration.yaml` are needed.

| Field | Example | Description |
|---|---|---|
| Wilma URL | `https://yourschool.inschool.fi` | Base URL of your school's Wilma instance |
| Username | `your@email.com` | Your Wilma login email |
| Password | | Your Wilma password |

The poll interval (default: 4 hours) can be changed after setup via the **Configure** button on the integration page.

### Credential storage

Credentials are stored in Home Assistant's config entry storage (`/.storage/core.config_entries`), which is encrypted at rest and never exposed through the HA UI or API. This is the standard HA mechanism used by all integrations that require authentication — the same way integrations like Spotify or Google handle credentials.

## Sensor attributes

Each sensor (`sensor.wilma_<child_name>`) exposes:

| Attribute | Description |
|---|---|
| `exams` | List of all upcoming exams |
| `next_exam` | The next upcoming exam |
| `next_exam_date` | ISO date of the next exam (e.g. `2026-04-20`) |

Each exam in the list has: `date`, `date_iso`, `topic`, `subject`, `group`, `teacher`, `details`.

## Automations

See [`docs/automations_example.yaml`](docs/automations_example.yaml) for example automations:
- Telegram notification on new exam
- Daily reminder 1 and 3 days before an exam
- `/exams` Telegram command to list all upcoming exams

## Disclaimer

This is an unofficial, personal open-source project and is not affiliated with, endorsed by, or connected to Visma or the Wilma school portal in any way. Use at your own risk. The author takes no responsibility for any issues arising from the use of this integration, including but not limited to data loss, incorrect data, or service disruptions.

## Tools

`tools/wilma_client.py` is a standalone test script for verifying connectivity and inspecting raw data without Home Assistant:

```bash
python tools/wilma_client.py
```
