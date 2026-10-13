# Credential client reuse

The environment/file credential ladder and key-shape check are adapted from Steve Brown's cc-speaks client. Willay passes the runtime value through that resolver after stricter owner-only/no-symlink file validation. It does not copy credentials, call the original summary TTS endpoint or invoke local playback. Public defaults use the Willay configuration directory; a deployment points ELEVENLABS_API_KEY_FILE at its existing vault-provisioned file. Dialogue and effects use a bounded HTTP boundary that refuses redirects and suppresses provider error bodies.
