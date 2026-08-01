export const organizationState = { organization: null, users: [], loaded: false };

export function setOrganizationData(organization, users) {
  organizationState.organization = organization;
  organizationState.users = users;
  organizationState.loaded = true;
}
