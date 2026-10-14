# Identity and Access

## Default

BSF Remote starts with local portal authentication. There is no public registration.

The bootstrap SUPERADMIN is created during deployment. Administrators create local remote users and assign roles.

Roles:

- SUPERADMIN
- ADMIN
- TECHNICIAN
- AUDITOR

## Optional Active Directory

AD/LDAPS is a secondary identity source. It is configured from the GUI after launch.

An AD account must have a corresponding PortalUser record with `auth_source=AD`, be active and be portal-enabled before it can authenticate. A valid AD password alone never creates a portal account.

Maintain a local SUPERADMIN as break-glass access.

## MFA

MFA is independent of the identity source and remains available for local and AD portal users. Unattended technician connections require step-up MFA according to the configured policy.
