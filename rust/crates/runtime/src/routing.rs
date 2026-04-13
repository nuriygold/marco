use std::collections::BTreeMap;
use std::time::Duration;

use crate::permissions::PermissionMode;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum CommandCapability {
    CoreAssistant,
    SystemTools,
    MothershipDomain,
}

impl CommandCapability {
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::CoreAssistant => "core_assistant",
            Self::SystemTools => "system_tools",
            Self::MothershipDomain => "mothership_domain",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResolvedCommandPolicy {
    pub capability: CommandCapability,
    pub safety_policy: PermissionMode,
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct CommandRouter;

impl CommandRouter {
    #[must_use]
    pub fn resolve(&self, command: &str) -> ResolvedCommandPolicy {
        if matches!(command, "bash" | "PowerShell" | "REPL") {
            return ResolvedCommandPolicy {
                capability: CommandCapability::SystemTools,
                safety_policy: PermissionMode::DangerFullAccess,
            };
        }

        if command.starts_with("mothership_") || command.starts_with("mothership__") {
            return ResolvedCommandPolicy {
                capability: CommandCapability::MothershipDomain,
                safety_policy: PermissionMode::WorkspaceWrite,
            };
        }

        ResolvedCommandPolicy {
            capability: CommandCapability::CoreAssistant,
            safety_policy: PermissionMode::ReadOnly,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct CapabilityTelemetry {
    samples: BTreeMap<CommandCapability, Vec<Duration>>,
    success: BTreeMap<CommandCapability, usize>,
    failure: BTreeMap<CommandCapability, usize>,
}

impl CapabilityTelemetry {
    pub fn record(&mut self, capability: CommandCapability, latency: Duration, ok: bool) {
        self.samples.entry(capability).or_default().push(latency);
        let target = if ok {
            &mut self.success
        } else {
            &mut self.failure
        };
        *target.entry(capability).or_default() += 1;
    }

    #[must_use]
    pub fn snapshot(&self) -> Vec<CapabilityTelemetryCounter> {
        let mut capabilities = self.samples.keys().copied().collect::<Vec<_>>();
        capabilities.sort_unstable();
        capabilities
            .into_iter()
            .map(|capability| {
                let samples = self.samples.get(&capability).cloned().unwrap_or_default();
                CapabilityTelemetryCounter {
                    capability,
                    success: self.success.get(&capability).copied().unwrap_or(0),
                    failure: self.failure.get(&capability).copied().unwrap_or(0),
                    median_latency_ms: median_duration_ms(&samples),
                }
            })
            .collect()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityTelemetryCounter {
    pub capability: CommandCapability,
    pub success: usize,
    pub failure: usize,
    pub median_latency_ms: u128,
}

fn median_duration_ms(samples: &[Duration]) -> u128 {
    if samples.is_empty() {
        return 0;
    }
    let mut sorted = samples.iter().map(Duration::as_millis).collect::<Vec<_>>();
    sorted.sort_unstable();
    sorted[sorted.len() / 2]
}

#[cfg(test)]
mod tests {
    use super::{CapabilityTelemetry, CommandCapability, CommandRouter};
    use std::time::Duration;

    #[test]
    fn resolves_core_and_system_and_mothership_commands() {
        let router = CommandRouter;

        assert_eq!(
            router.resolve("read_file").capability,
            CommandCapability::CoreAssistant
        );
        assert_eq!(
            router.resolve("bash").capability,
            CommandCapability::SystemTools
        );
        assert_eq!(
            router.resolve("mothership_sync").capability,
            CommandCapability::MothershipDomain
        );
    }

    #[test]
    fn reports_median_latency_and_success_failure_counts() {
        let mut telemetry = CapabilityTelemetry::default();
        telemetry.record(
            CommandCapability::CoreAssistant,
            Duration::from_millis(40),
            true,
        );
        telemetry.record(
            CommandCapability::CoreAssistant,
            Duration::from_millis(15),
            false,
        );
        telemetry.record(
            CommandCapability::CoreAssistant,
            Duration::from_millis(25),
            true,
        );

        let snapshot = telemetry.snapshot();
        assert_eq!(snapshot.len(), 1);
        assert_eq!(snapshot[0].success, 2);
        assert_eq!(snapshot[0].failure, 1);
        assert_eq!(snapshot[0].median_latency_ms, 25);
    }
}
