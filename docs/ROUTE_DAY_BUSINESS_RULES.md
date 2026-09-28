# Route Day Business Rules

These rules are product invariants for any trip day that represents movement along a route rather than a single-city stay.

1. A route day is a continuous journey, not a hotel-centered map.
2. Day N starts where Day N-1 ended.
3. The map for Day N shows every previous planned route segment from the beginning of the trip in gray.
4. The current day segment is highlighted in gold.
5. Morning activity belongs near the start of the day route.
6. Noon activity belongs around the early/middle part of the day route.
7. Evening activity belongs around the late part of the day route.
8. Night activity belongs near the end of the day route.
9. Activities must not move backward along the route unless the traveler explicitly edits the plan that way.
10. Hotels and stay bases do not define the route-day path unless the traveler explicitly sets them as the day start or end.
11. Distances shown on route days are route distances from the day start and leg distances from the previous stop.
12. Showcase and demo data must obey the same route rules as live-generated data.
13. If exact venue coordinates are clustered but the itinerary is a route day, the map may visualize the stop at its route-progress position while details and directions preserve the real venue coordinates.
14. Any future route feature must include a check against these rules before it is considered complete.

