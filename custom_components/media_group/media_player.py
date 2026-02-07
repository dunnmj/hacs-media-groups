"""Media player platform for Media Group."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    SERVICE_SELECT_SOURCE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_ENTITIES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Media Group from a config entry."""
    entities = config_entry.options[CONF_ENTITIES]
    async_add_entities(
        [MediaGroupPlayer(config_entry.entry_id, config_entry.title, entities)]
    )


class MediaGroupPlayer(MediaPlayerEntity):
    """A media player that aggregates sources from multiple media players."""

    _attr_icon = "mdi:speaker-multiple"
    _attr_should_poll = False
    _attr_available = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(self, unique_id: str, name: str, entities: list[str]) -> None:
        """Initialize the media group player."""
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._entities = entities

        # Maps "display source name" -> list of (entity_id, original_source_name)
        self._source_mapping: dict[str, list[tuple[str, str]]] = {}
        self._attr_source_list: list[str] = []
        self._attr_source: str | None = None

    async def async_added_to_hass(self) -> None:
        """Register state change listeners."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._entities, self._async_on_state_change
            )
        )
        self._async_rebuild_source_list()
        self._async_update_state()
        self.async_write_ha_state()

    @callback
    def _async_on_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle a member entity state change."""
        self._async_rebuild_source_list()
        self._async_update_state()
        self.async_write_ha_state()

    @callback
    def _async_rebuild_source_list(self) -> None:
        """Rebuild the aggregated source list from all member entities.

        Sources shared by all available members are listed by name only.
        Sources unique to a subset of members are prefixed with the entity name.
        """
        # First pass: collect source -> list of (entity_id, entity_name) that have it
        source_owners: dict[str, list[tuple[str, str]]] = {}
        available_entity_ids: set[str] = set()

        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state == STATE_UNAVAILABLE:
                continue

            available_entity_ids.add(entity_id)
            entity_name = state.name or entity_id
            sources = state.attributes.get(ATTR_INPUT_SOURCE_LIST, [])

            for source in sources:
                source_owners.setdefault(source, []).append((entity_id, entity_name))

        # Second pass: build display names
        self._source_mapping = {}
        source_list: list[str] = []

        # Sources that appear on every available entity are "shared"
        num_available = len(available_entity_ids)

        for source, owners in source_owners.items():
            if len(owners) == num_available and num_available > 0:
                # Shared source — display without prefix
                display_name = source
                self._source_mapping[display_name] = [
                    (eid, source) for eid, _ in owners
                ]
                source_list.append(display_name)
            else:
                # Unique source — prefix with entity name
                for entity_id, entity_name in owners:
                    display_name = f"{entity_name} - {source}"
                    self._source_mapping.setdefault(display_name, []).append(
                        (entity_id, source)
                    )
                    source_list.append(display_name)

        self._attr_source_list = source_list

        # Update current source based on what members have selected
        self._async_update_current_source()

    @callback
    def _async_update_current_source(self) -> None:
        """Determine the current source from member states."""
        # Build a reverse lookup: (entity_id, source) -> display_name
        reverse: dict[tuple[str, str], str] = {}
        for display_name, targets in self._source_mapping.items():
            for entity_id, source in targets:
                reverse[(entity_id, source)] = display_name

        active_display: set[str] = set()
        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state == STATE_UNAVAILABLE:
                continue

            current_source = state.attributes.get(ATTR_INPUT_SOURCE)
            if current_source is None:
                continue

            key = (entity_id, current_source)
            if key in reverse:
                active_display.add(reverse[key])

        if len(active_display) == 1:
            self._attr_source = next(iter(active_display))
        elif len(active_display) > 1:
            self._attr_source = sorted(active_display)[0]
        else:
            self._attr_source = None

    @callback
    def _async_update_state(self) -> None:
        """Update group state from members."""
        states = [
            state.state
            for entity_id in self._entities
            if (state := self.hass.states.get(entity_id)) is not None
        ]

        self._attr_available = any(s != STATE_UNAVAILABLE for s in states)

        valid_states = [
            s for s in states if s not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        ]
        if not valid_states:
            self._attr_state = None
            return

        # Aggregate volume from available members
        volumes: list[float] = []
        muted_values: list[bool] = []
        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            vol_level = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
            if vol_level is not None:
                volumes.append(vol_level)
            vol_muted = state.attributes.get(ATTR_MEDIA_VOLUME_MUTED)
            if vol_muted is not None:
                muted_values.append(vol_muted)

        if volumes:
            self._attr_volume_level = sum(volumes) / len(volumes)
        else:
            self._attr_volume_level = None

        if muted_values:
            self._attr_is_volume_muted = all(muted_values)
        else:
            self._attr_is_volume_muted = None

        self._attr_state = MediaPlayerState.ON

    async def async_select_source(self, source: str) -> None:
        """Select a source on all mapped member entities."""
        if source not in self._source_mapping:
            _LOGGER.error("Unknown source: %s", source)
            return

        targets = self._source_mapping[source]
        for entity_id, original_source in targets:
            await self.hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                SERVICE_SELECT_SOURCE,
                {
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_INPUT_SOURCE: original_source,
                },
                context=self._context,
            )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume on all member entities."""
        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            if features & MediaPlayerEntityFeature.VOLUME_SET:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    SERVICE_VOLUME_SET,
                    {
                        ATTR_ENTITY_ID: entity_id,
                        ATTR_MEDIA_VOLUME_LEVEL: volume,
                    },
                    context=self._context,
                )

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute/unmute all member entities."""
        for entity_id in self._entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            if features & MediaPlayerEntityFeature.VOLUME_MUTE:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    SERVICE_VOLUME_MUTE,
                    {
                        ATTR_ENTITY_ID: entity_id,
                        ATTR_MEDIA_VOLUME_MUTED: mute,
                    },
                    context=self._context,
                )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {ATTR_ENTITY_ID: self._entities}
