use std::collections::BTreeSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum DomainNamespace {
    Task,
    Email,
    Finance,
    Dispatch,
    Approve,
}

impl DomainNamespace {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Task => "task",
            Self::Email => "email",
            Self::Finance => "finance",
            Self::Dispatch => "dispatch",
            Self::Approve => "approve",
        }
    }

    fn parse(value: &str) -> Option<Self> {
        match value {
            "task" => Some(Self::Task),
            "email" => Some(Self::Email),
            "finance" => Some(Self::Finance),
            "dispatch" => Some(Self::Dispatch),
            "approve" => Some(Self::Approve),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DomainVerb {
    Start,
    Stop,
    List,
    Status,
    Send,
    Create,
    Approve,
    Reject,
    Unknown(String),
}

impl DomainVerb {
    fn parse(value: &str) -> Self {
        match value {
            "start" => Self::Start,
            "stop" => Self::Stop,
            "list" => Self::List,
            "status" => Self::Status,
            "send" => Self::Send,
            "create" => Self::Create,
            "approve" => Self::Approve,
            "reject" => Self::Reject,
            other => Self::Unknown(other.to_string()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DomainAction {
    pub verb: DomainVerb,
    pub primary_arg: Option<String>,
    pub extra_args: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DomainCommand {
    Task(DomainAction),
    Email(DomainAction),
    Finance(DomainAction),
    Dispatch(DomainAction),
    Approve(DomainAction),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DomainCommandRegistry {
    enabled: BTreeSet<DomainNamespace>,
}

impl Default for DomainCommandRegistry {
    fn default() -> Self {
        Self::all_enabled()
    }
}

impl DomainCommandRegistry {
    #[must_use]
    pub fn all_enabled() -> Self {
        Self {
            enabled: [
                DomainNamespace::Task,
                DomainNamespace::Email,
                DomainNamespace::Finance,
                DomainNamespace::Dispatch,
                DomainNamespace::Approve,
            ]
            .into_iter()
            .collect(),
        }
    }

    #[must_use]
    pub fn with_enabled(enabled: impl IntoIterator<Item = DomainNamespace>) -> Self {
        Self {
            enabled: enabled.into_iter().collect(),
        }
    }

    #[must_use]
    pub fn parse(&self, input: &str) -> Option<DomainCommand> {
        let mut parts = input.trim().trim_start_matches('/').split_whitespace();
        let namespace = DomainNamespace::parse(parts.next()?)?;
        if !self.enabled.contains(&namespace) {
            return None;
        }

        let verb = DomainVerb::parse(parts.next().unwrap_or("status"));
        let primary_arg = parts.next().map(ToOwned::to_owned);
        let extra_args = parts.map(ToOwned::to_owned).collect::<Vec<_>>();
        let action = DomainAction {
            verb,
            primary_arg,
            extra_args,
        };

        Some(match namespace {
            DomainNamespace::Task => DomainCommand::Task(action),
            DomainNamespace::Email => DomainCommand::Email(action),
            DomainNamespace::Finance => DomainCommand::Finance(action),
            DomainNamespace::Dispatch => DomainCommand::Dispatch(action),
            DomainNamespace::Approve => DomainCommand::Approve(action),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{DomainAction, DomainCommand, DomainCommandRegistry, DomainNamespace, DomainVerb};

    #[test]
    fn parses_task_start_command() {
        let registry = DomainCommandRegistry::all_enabled();
        let parsed = registry.parse("/task start abc-123");
        assert_eq!(
            parsed,
            Some(DomainCommand::Task(DomainAction {
                verb: DomainVerb::Start,
                primary_arg: Some("abc-123".to_string()),
                extra_args: Vec::new(),
            }))
        );
    }

    #[test]
    fn registry_can_disable_specific_domain_commands() {
        let registry = DomainCommandRegistry::with_enabled([DomainNamespace::Task]);
        assert!(registry.parse("/task start abc-123").is_some());
        assert!(registry.parse("/email send welcome").is_none());
    }
}
