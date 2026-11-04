// Account identity is always the workspace ID, never a directory or display name.
function defaultWorkspace(product, currentId, preferences) {
  const accounts = product.workspaces.filter(w => w.assigned);
  if (product.workspaces.some(w => w.id === currentId)) return currentId;
  if (Object.prototype.hasOwnProperty.call(preferences, product.id)) {
    const saved = preferences[product.id];
    if (saved === '') return null;
    if (accounts.some(w => w.id === saved)) return saved;
  }
  const normalize = name => String(name).normalize('NFKC').trim().toLowerCase();
  const matches = accounts.filter(w => normalize(w.name) === normalize(product.name));
  return matches.length === 1 ? matches[0].id : null;
}
if (typeof module !== 'undefined') module.exports = {defaultWorkspace};
