// Route identifiers only; market data and company details always come from the API.
// Keep this list aligned with backend/app/domain/company_universe.py.
export const SUPPORTED_COMPANY_SYMBOLS = [
  "ALI",
  "APX",
  "BPI",
  "GLO",
  "ICT",
  "JFC",
  "MBT",
  "MEG",
  "MER",
  "NIKL",
  "PGOLD",
  "SCC",
  "SECB",
  "SHLPH",
  "SMPH",
] as const;
