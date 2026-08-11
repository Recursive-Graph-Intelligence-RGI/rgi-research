use std::path::{Path, PathBuf};
use std::process::Command;

/// FortSignal-style hard boundary for the Tauri sidecar example.
///
/// Before the Rust shell spawns the RGI Python engine, it validates that the
/// user-selected workspace stays inside an allowed root and passes the policy
/// down to RGI via environment variables. This is the OS-shell half of the
/// governance model; the Python engine implements the semantic half.
#[derive(Debug, Clone)]
pub struct Governance {
    pub allowed_root: PathBuf,
    pub policy_file: Option<PathBuf>,
    pub max_llm_calls: usize,
    pub allow_spawn: bool,
}

impl Governance {
    /// Build governance defaults from an allowed root.
    pub fn new(allowed_root: impl AsRef<Path>) -> Self {
        Self {
            allowed_root: allowed_root.as_ref().to_path_buf(),
            policy_file: None,
            max_llm_calls: 20,
            allow_spawn: true,
        }
    }

    /// Load a policy file (JSON) if present. Missing files are ignored so the
    /// example stays runnable without configuration.
    pub fn with_policy_file(mut self, path: impl AsRef<Path>) -> Self {
        self.policy_file = Some(path.as_ref().to_path_buf());
        self
    }

    /// Return true if `target` is inside the allowed root.
    pub fn path_allowed(&self, target: &Path) -> bool {
        let abs_root = self.allowed_root.canonicalize().unwrap_or_else(|_| self.allowed_root.clone());
        let abs_target = target.canonicalize().unwrap_or_else(|_| target.to_path_buf());
        abs_target.starts_with(&abs_root)
    }

    /// Apply policy environment variables to the RGI child process command.
    pub fn apply_to(&self, cmd: &mut Command) {
        cmd.env("RGI_ALLOWED_ROOT", &self.allowed_root);
        cmd.env("RGI_MAX_LLM_CALLS", self.max_llm_calls.to_string());
        cmd.env("RGI_ALLOW_SPAWN", self.allow_spawn.to_string());
        if let Some(policy) = &self.policy_file {
            cmd.env("RGI_POLICY_FILE", policy);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn path_inside_allowed_root_is_allowed() {
        let gov = Governance::new("/home/user/projects");
        assert!(gov.path_allowed(Path::new("/home/user/projects/app/main.py")));
    }

    #[test]
    fn path_outside_allowed_root_is_denied() {
        let gov = Governance::new("/home/user/projects");
        assert!(!gov.path_allowed(Path::new("/etc/passwd")));
    }
}
