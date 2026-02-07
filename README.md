# Media Group — Home Assistant Custom Integration (HACS)

Combine multiple media players into a single entity with an aggregated source list.

---

## Overview

- **Domain:** `media_group`
- **Platform:** `media_player`
- **Configuration:** GUI (Settings → Devices & Services → Helpers)
- **Type:** Helper integration

This integration creates a virtual media player that collects the source lists from all member media players into one combined source selector. Selecting a source routes the command to the correct underlying media player.

---

## Features

- **Aggregated source list** — all sources from all member media players appear in one dropdown
- **Source routing** — selecting a source sends the command to the correct member entity
- **Volume control** — set volume or mute/unmute across all members
- **Real-time updates** — the group updates whenever a member entity changes
- **GUI setup** — add and configure from the Helpers page, no YAML needed
- **Editable** — change group members at any time via the options flow

---

## Installation (HACS)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Open the menu (⋮) → **Custom repositories**
4. Add:
   - **Repository:** `https://github.com/dunnmj/hacs-media-groups`
   - **Category:** Integration
5. Search for **Media Group**
6. Install and **restart Home Assistant**

---

## Setup

1. Go to **Settings → Devices & Services → Helpers**
2. Click **Create Helper**
3. Select **Media Group**
4. Enter a name and select the media players to include
5. Click **Submit**

A new `media_player` entity will be created with sources from all selected members.

---

## How it works

### Source list

The group entity builds a combined source list from all member media players. Each source is prefixed with the member entity's friendly name to avoid collisions:

```
Living Room Speaker - Spotify
Living Room Speaker - AirPlay
Kitchen Speaker - Spotify
Kitchen Speaker - Line In
```

### Source selection

When you select a source, the integration determines which member entity owns that source and sends the `media_player.select_source` command to it.

### Volume and mute

Volume and mute commands are sent to **all** member entities that support them. The displayed volume level is the average across all members.

### State

The group entity shows as `on` if any member entity is available with a valid state.

---

## Editing

To change which media players are in the group:

1. Go to **Settings → Devices & Services → Helpers**
2. Find your media group
3. Click **Configure**
4. Update the member list
5. Click **Submit**

The group entity will reload with the updated members.

---

## Support / Issues

Please open GitHub issues with:

- Your Home Assistant version
- Relevant debug logs
- The member entities in your group
