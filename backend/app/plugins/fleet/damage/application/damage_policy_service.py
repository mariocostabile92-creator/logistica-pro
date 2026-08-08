from app.plugins.fleet.damage.domain.damage_policy import DamagePolicy
from app.plugins.fleet.damage.infrastructure import damage_policy_repository


def current_policy(organization_id: str) -> DamagePolicy:
    return damage_policy_repository.get_policy(organization_id) or DamagePolicy(
        organization_id=organization_id,
    )


def save_policy(policy: DamagePolicy) -> DamagePolicy:
    return damage_policy_repository.save_policy(policy)

