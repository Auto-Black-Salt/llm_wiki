# leg_event

**Summary**

The `leg_event` table is a denormalized event stream that captures all changes to the *leg* business entity from the Ops‑DM warehouse.  
It is produced by an extended streaming job that reads CDC from normalized tables (`ops_dm_common.leg`, `ops_dm_common.leg_delay`, `ops_dm_common.people_on_leg`, etc.), performs the necessary joins, and writes a single event per change.  
Key benefits are:

- **Single source of truth for consumers** – one stream instead of 4‑5 separate CDC feeds.  
- **Low latency** – events are emitted within ~2 min of the source change.  
- **No separate maintenance job** – integrated into the existing Standard‑to‑Curated pipeline.  
- **Nested schema** – avoids column name ambiguity and preserves original field names.

**Schema**

| Field | Type | Description |
|-------|------|-------------|
| `leg_id` *(PK)* | `uuid5` | Identifier of the leg |
| `event_timestamp` *(PK)* | `timestamp` | Timestamp when event was created (matches `leg.source_timestamp`) |
| `event_type` | `string or struct` | Optional classification (e.g., CXX, DIV). Not yet used. |
| `airline_designator` | `struct` | MDS airline entity linked to flight ID/date |
| `departure_airport` | `struct` | MDS airport entity for departure |
| `arrival_airport` | `struct` | MDS airport entity for arrival |
| `leg` | `struct` | Current state of the leg record |
| `leg_delay` | `array<variant>` | Array of valid leg‑delay entities at event time |
| `people_on_leg` | `struct` | Current people_on_leg record |
| `people_on_leg_compartment` | `variant<map<string, struct>>` | Map of compartment entities at event time |

*Additional fields can be added later without breaking downstream consumers.*

**Usage Patterns**

