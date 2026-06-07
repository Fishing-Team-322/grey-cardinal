import { api } from "./api.js";

export async function getCurrentUser() {
  const [user, context] = await Promise.all([api.auth.me(), api.context()]);
  return { ...user, companies: context.companies || [], teams: context.teams || [] };
}

export function homeForUser(user) {
  const directed = user.companies?.filter((company) => company.role === "director") || [];
  if (directed.length === 1) return `/app/companies/${directed[0].id}`;
  if (directed.length > 1 || (!directed.length && !user.teams?.length)) return "/app/companies";
  const managed = user.teams?.find((team) => team.role === "manager");
  return managed ? `/app/teams/${managed.id}` : "/app/employee";
}

export function roleForUser(user) {
  if (user.companies?.some((company) => company.role === "director")) return "director";
  if (user.teams?.some((team) => team.role === "manager")) return "manager";
  return "employee";
}

export function guardFor(...roles) {
  return async () => {
    const user = window.gcCurrentUser;
    if (
      roles.includes("director")
      && !user.companies?.length
      && (location.pathname === "/app/companies" || location.pathname === "/app/companies/")
    ) {
      return true;
    }
    return roles.includes(roleForUser(user)) ? true : homeForUser(user);
  };
}
