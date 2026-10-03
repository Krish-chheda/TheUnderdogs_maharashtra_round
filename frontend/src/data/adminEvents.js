export const lifecycle = {
  DRAFT: "DRAFT",
  REGISTRATION_OPEN: "REGISTRATION_OPEN",
  REGISTRATION_CLOSED: "REGISTRATION_CLOSED",
  ALLOCATION_RUNNING: "ALLOCATION_RUNNING",
  ALLOCATION_COMPLETED: "ALLOCATION_COMPLETED",
  CLAIMS_OPEN: "CLAIMS_OPEN",
  COMPLETED: "COMPLETED",
};

export const initialAdminEvents = [
  {
    id: "summit-2026",
    name: "Signal / Summit 2026",
    capacity: 1200,
    totalEntries: 874,
    status: lifecycle.REGISTRATION_OPEN,
    registrationDeadline: "2026-11-01T23:59:00",
  },
  {
    id: "night-market",
    name: "Night Market / Vol. 04",
    capacity: 800,
    totalEntries: 800,
    status: lifecycle.REGISTRATION_CLOSED,
    registrationDeadline: "2026-10-18T23:59:00",
  },
  {
    id: "open-source-lab",
    name: "Open Source Lab",
    capacity: 300,
    totalEntries: 126,
    status: lifecycle.ALLOCATION_COMPLETED,
    registrationDeadline: "2026-11-28T23:59:00",
  },
];

export const initialAdminMetrics = {
  totalEntries: 1800,
  seatsRemaining: 500,
  requestsPerSecond: 42.8,
  claimsProcessed: 326,
  rateLimited: 18,
  blocked: 4,
};

export const initialIntegrity = {
  winnersGenerated: 300,
  duplicateWinners: 0,
  oversells: 0,
  successfulClaims: 286,
  failedClaims: 14,
};

export const trafficSeries = [
  { time: "12:00", incoming: 18, limited: 2, blocked: 0 },
  { time: "12:05", incoming: 31, limited: 4, blocked: 1 },
  { time: "12:10", incoming: 27, limited: 3, blocked: 0 },
  { time: "12:15", incoming: 48, limited: 7, blocked: 2 },
  { time: "12:20", incoming: 39, limited: 5, blocked: 1 },
  { time: "12:25", incoming: 58, limited: 9, blocked: 3 },
  { time: "12:30", incoming: 43, limited: 6, blocked: 1 },
];
