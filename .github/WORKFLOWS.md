# GitHub Actions Workflows

This repository includes several GitHub Actions workflows for automated testing, building, and releasing the GEO MCP Server package.

## Workflows

### 1. Test and Build (`test.yml`)
- **Triggers**: Push to `main`/`develop` branches, Pull Requests to `main`
- **Purpose**: Runs tests across multiple Python versions and builds the package
- **Actions**:
  - Tests the package on Python 3.9, 3.10, 3.11, and 3.12
  - Builds the package (only on pushes to main)
  - Uploads build artifacts

### 2. Release Package (`release.yml`)
- **Triggers**: When a GitHub release is published
- **Purpose**: Publishes stable releases to PyPI
- **Actions**:
  - Builds the package
  - Publishes to PyPI
  - Creates GitHub release assets

### 3. Development Release (`dev-release.yml`)
- **Triggers**: When a GitHub pre-release is published (tags containing `dev`, `alpha`, `beta`, or `rc`)
- **Purpose**: Publishes development releases to TestPyPI
- **Actions**:
  - Builds the package
  - Publishes to TestPyPI
  - Creates GitHub pre-release assets

## Setup Instructions

### 1. PyPI API Token
To publish to PyPI, you need to create an API token:

1. Go to [PyPI Account Settings](https://pypi.org/manage/account/)
2. Create a new API token with "Entire account" scope
3. Add the token to your GitHub repository secrets:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Create a new secret named `PYPI_API_TOKEN`
   - Paste your PyPI API token

### 2. TestPyPI API Token (Optional)
For development releases, you can also set up TestPyPI:

1. Go to [TestPyPI Account Settings](https://test.pypi.org/manage/account/)
2. Create a new API token
3. Add the token to your GitHub repository secrets as `TEST_PYPI_API_TOKEN`

### 3. GitHub Token
The `GITHUB_TOKEN` is automatically provided by GitHub Actions, so no setup is needed.

## Usage

### Creating a Release
1. Create a new release on GitHub
2. Tag it with a version number (e.g., `v1.0.0`)
3. Publish the release
4. The workflow will automatically build and publish to PyPI

### Creating a Development Release
1. Create a new release on GitHub
2. Tag it with a development version (e.g., `v1.0.0-dev.1`, `v1.0.0-alpha.1`)
3. Mark it as a pre-release
4. Publish the release
5. The workflow will automatically build and publish to TestPyPI

### Testing
- Push to `main` or `develop` branches to trigger tests
- Create pull requests to `main` to trigger tests
- Tests run on multiple Python versions to ensure compatibility

## Version Management

The package uses [hatch-vcs](https://github.com/ofek/hatch-vcs) for automatic version detection from git tags. The version format follows PEP 440:

- `0.1.dev1+g91ddaa4.d20250623` - Development version
- `0.1.0` - Stable release
- `0.1.0-dev.1` - Development release
- `0.1.0-alpha.1` - Alpha release
- `0.1.0-beta.1` - Beta release
- `0.1.0-rc.1` - Release candidate

## Troubleshooting

### Common Issues

1. **Build fails**: Check that all dependencies are properly specified in `pyproject.toml`
2. **PyPI upload fails**: Verify your `PYPI_API_TOKEN` is correct and has proper permissions
3. **Tests fail**: Ensure all test dependencies are installed and tests are properly configured

### Manual Release
If you need to release manually:

```bash
# Build the package
python -m build

# Check the package
twine check dist/*

# Upload to PyPI
twine upload dist/*

# Upload to TestPyPI (for development releases)
twine upload --repository testpypi dist/*
``` 