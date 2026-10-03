export const events = [
  {
    id: "summit-2026",
    name: "Signal / Summit 2026",
    description:
      "A two-day gathering for builders shaping the next layer of public technology.",
    date: "2026-11-14T09:00:00",
    timezone: "IST",
    registrationDeadline: "2026-11-01T23:59:00",
    capacity: 1200,
    entryCount: 874,
    status: "Open",
    venue: "Bandra Kurla Complex, Mumbai",
    accent: "cyan",
  },
  {
    id: "night-market",
    name: "Night Market / Vol. 04",
    description:
      "Independent makers, late-night sets, and 80 limited entry windows.",
    date: "2026-10-24T18:30:00",
    timezone: "IST",
    registrationDeadline: "2026-10-18T23:59:00",
    capacity: 800,
    entryCount: 800,
    status: "Closed",
    venue: "Mill District, Pune",
    accent: "violet",
  },
  {
    id: "open-source-lab",
    name: "Open Source Lab",
    description:
      "A focused working session for maintainers, contributors, and curious minds.",
    date: "2026-12-05T10:00:00",
    timezone: "IST",
    registrationDeadline: "2026-11-28T23:59:00",
    capacity: 300,
    entryCount: 126,
    status: "Open",
    venue: "Online + The Workshop, Bengaluru",
    accent: "blue",
  },
];

export const myEvents = [
  {
    ...events[0],
    status: "Eligible",
    action: "View status",
  },
  {
    ...events[2],
    status: "Registered",
    action: "View event",
  },
];
