# ChangeLog

## v1.3.0

## v1.3.0-pre1
* #[47](https://github.com/vrivellino/spoptimize/pull/47): Fix coveralls badge URL
* #[46](https://github.com/vrivellino/spoptimize/pull/46): Quick Launch button / nested stack
* #[44](https://github.com/vrivellino/spoptimize/pull/44): Increased test coverage [Follow-up to #41]
* #[43](https://github.com/vrivellino/spoptimize/pull/43): Properly handle launch notifications from attached
    instances. (Fix for bug introduced in #40.)
* #[41](https://github.com/vrivellino/spoptimize/pull/41): Improved test coverage
* #[40](https://github.com/vrivellino/spoptimize/pull/40): Allow for missing SubnetId [Follow-up to #39]
* #[39](https://github.com/vrivellino/spoptimize/pull/39): Support security-group names in launch-config for
  EC2-Classic support
* #[38](https://github.com/vrivellino/spoptimize/pull/38): Use auto-scaling instance protection for min OD via
  `spoptimize:min_protected_instances` tag [Implements #23]
* New IAM privs: `autoscaling:SetInstanceProtection`, `ec2:DescribeSecurityGroups`

## v1.2.1
* #[37](https://github.com/vrivellino/spoptimize/pull/37): Deploy.sh fix

## v1.2.0
* #[35](https://github.com/vrivellino/spoptimize/pull/35): Release helper and Change Log
* #[34](https://github.com/vrivellino/spoptimize/pull/34): Don't loop after checking ASG instance health
* #[33](https://github.com/vrivellino/spoptimize/pull/33): Reduce size of step function state
* #[32](https://github.com/vrivellino/spoptimize/pull/32): Centralize static strings in a module [Related to #22]
* #[31](https://github.com/vrivellino/spoptimize/pull/31): Add yamllint to tests
* #[30](https://github.com/vrivellino/spoptimize/pull/30): Demo ASG that uses spoptimize

## v1.1.0
* #[28](https://github.com/vrivellino/spoptimize/pull/28): Deploy enhancements
  - Add argument for cfn package step
  - Support stack tags via environment variables
  - Add awscli >= 1.14.31 to dev(/deploy) requirements

## v1.0.0

Initial Release
