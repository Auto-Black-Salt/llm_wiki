# Schema of leg_event entity

| Field | Type | Description |
|-------|------|-------------|
| `leg_id` (PK) | uuid5 | Identifier of the leg |
| `event_timestamp` (PK) | timestamp | Event creation timestamp (`leg.source_timestamp`) |
| `event_type` | string or struct | Future classification (e.g., CXX, DIV) – not yet implemented |
| `airline_designator` | struct | Matching airline entity from MDS (`flight_id_date`, `airline_designator_id`) |
| `departure_airport` | struct | Matching airport entity from MDS (`flight_id_date`, `departure_airport_id`) |
| `arrival_airport` | struct | Matching airport entity from MDS (`flight_id_date`, `arrival_airport_id`) |
| `leg` | struct | Current leg entity at event time |
| `leg_delay` | array<struct> | Available `leg_delay` entities valid at event timestamp (variant type for evolution) |
| `people_on_leg` | struct | Current people_on_leg entity at event time |
| `people_on_leg_compartment` | map<string, struct> | Available `people_on_leg_compartment` entities at event timestamp (variant type) |
| … | – | Additional nested entities can be added later |

