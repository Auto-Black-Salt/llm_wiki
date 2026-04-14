# leg_event

- **Type**: Entity  
- **Description**: The `leg_event` table stores denormalized change events for the *Leg* business entity.  
- **Key columns**: `leg_id` (UUID5), `event_timestamp` (timestamp).  
- **Structure**: Nested structs for related entities (`airline_designator`, `departure_airport`, `arrival_airport`, `leg`, `leg_delay`, `people_on_leg`, `people_on_leg_compartment`).  
- **Use cases**:  
  - Query all events for a given time range.  
  - Filter by specific leg or nested attributes (e.g., `leg.cancellation_indicator`).  
- **Sources**: [[Leg Event table-v10-20260413_154944.pdf]](leg-event-table.md)

