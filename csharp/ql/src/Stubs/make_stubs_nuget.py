import sys
import os
import helpers
import json
import shutil


def write_csproj_prefix(ioWrapper):
    ioWrapper.write('<Project Sdk="Microsoft.NET.Sdk">\n')
    ioWrapper.write('  <PropertyGroup>\n')
    ioWrapper.write('    <TargetFramework>net7.0</TargetFramework>\n')
    ioWrapper.write('    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>\n')
    ioWrapper.write('    <OutputPath>bin\</OutputPath>\n')
    ioWrapper.write(
        '    <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>\n')
    ioWrapper.write('  </PropertyGroup>\n\n')


print('Script to generate stub file from a nuget package')
print(' Usage: python3 ' + sys.argv[0] +
      ' TEMPLATE NUGET_PACKAGE_NAME [VERSION=latest] [WORK_DIR=tempDir]')
print(' The script uses the dotnet cli, codeql cli, and dotnet format global tool')
print(' TEMPLATE should be either classlib or webapp, depending on the nuget package. For example, `Swashbuckle.AspNetCore.Swagger` should use `webapp` while `newtonsoft.json` should use `classlib`.')

if len(sys.argv) < 2:
    print("\nPlease supply a template name.")
    exit(1)

if len(sys.argv) < 3:
    print("\nPlease supply a nuget package name.")
    exit(1)

thisScript = sys.argv[0]
thisDir = os.path.abspath(os.path.dirname(thisScript))
template = sys.argv[1]
nuget = sys.argv[2]

# /input contains a dotnet project that's being extracted
workDir = os.path.abspath(helpers.get_argv(4, "tempDir"))
projectNameIn = "input"
projectDirIn = os.path.join(workDir, projectNameIn)

def run_cmd(cmd, msg="Failed to run command"):
    helpers.run_cmd_cwd(cmd, workDir, msg)

# /output contains the output of the stub generation
outputDirName = "output"
outputDir = os.path.join(workDir, outputDirName)

# /output/raw contains the bqrs result from the query, the json equivalent
rawOutputDirName = "raw"
rawOutputDir = os.path.join(outputDir, rawOutputDirName)
os.makedirs(rawOutputDir)

# /output/output contains a dotnet project with the generated stubs
projectNameOut = "output"
projectDirOut = os.path.join(outputDir, projectNameOut)

# /db contains the extracted QL DB
dbName = 'db'
dbDir = os.path.join(workDir, dbName)
outputName = "stub"
outputFile = os.path.join(projectDirOut, outputName + '.cs')
bqrsFile = os.path.join(rawOutputDir, outputName + '.bqrs')
jsonFile = os.path.join(rawOutputDir, outputName + '.json')
version = helpers.get_argv(3, "latest")

print("\n* Creating new input project")
run_cmd(['dotnet', 'new', template, "-f", "net7.0", "--language", "C#", '--name',
                 projectNameIn, '--output', projectDirIn])
helpers.remove_files(projectDirIn, '.cs')

print("\n* Adding reference to package: " + nuget)
cmd = ['dotnet', 'add', projectDirIn, 'package', nuget]
if (version != "latest"):
    cmd.append('--version')
    cmd.append(version)
run_cmd(cmd)

sdk_version = '7.0.102'
print("\n* Creating new global.json file and setting SDK to " + sdk_version)
run_cmd(['dotnet', 'new', 'globaljson', '--force', '--sdk-version', sdk_version, '--output', workDir])

print("\n* Running stub generator")
helpers.run_cmd_cwd(['dotnet', 'run', '--project', thisDir + '/../../../extractor/Semmle.Extraction.CSharp.DependencyStubGenerator/Semmle.Extraction.CSharp.DependencyStubGenerator.csproj'], projectDirIn)

print("\n* Creating new raw output project")
rawSrcOutputDirName = 'src'
rawSrcOutputDir = os.path.join(rawOutputDir, rawSrcOutputDirName)
run_cmd(['dotnet', 'new', template, "--language", "C#",
                '--name', rawSrcOutputDirName, '--output', rawSrcOutputDir])
helpers.remove_files(rawSrcOutputDir, '.cs')

# copy each file from projectDirIn to rawSrcOutputDir
pathInfos = {}
codeqlStubsDir = os.path.join(projectDirIn, 'codeql_csharp_stubs')
for root, dirs, files in os.walk(codeqlStubsDir):
    for file in files:
        if file.endswith('.cs'):
            path = os.path.join(root, file)
            relPath, _ = os.path.splitext(os.path.relpath(path, codeqlStubsDir))
            origDllPath = "/" + relPath + ".dll"
            pathInfos[origDllPath] = os.path.join(rawSrcOutputDir, file)
            shutil.copy2(path, rawSrcOutputDir)

print("\n --> Generated stub files: " + rawSrcOutputDir)

print("\n* Formatting files")
run_cmd(['dotnet', 'format', 'whitespace', rawSrcOutputDir])

print("\n --> Generated (formatted) stub files: " + rawSrcOutputDir)

print("\n* Processing project.assets.json to generate folder structure")
stubsDirName = 'stubs'
stubsDir = os.path.join(outputDir, stubsDirName)
os.makedirs(stubsDir)

frameworksDirName = '_frameworks'
frameworksDir = os.path.join(stubsDir, frameworksDirName)

frameworks = set()
copiedFiles = set()

assetsJsonFile = os.path.join(projectDirIn, 'obj', 'project.assets.json')
with open(assetsJsonFile) as json_data:
    data = json.load(json_data)
    if len(data['targets']) > 1:
        print("ERROR: More than one target found in " + assetsJsonFile)
        exit(1)
    target = list(data['targets'].keys())[0]
    print("Found target: " + target)
    for package in data['targets'][target].keys():
        parts = package.split('/')
        name = parts[0]
        version = parts[1]
        packageDir = os.path.join(stubsDir, name, version)
        if not os.path.exists(packageDir):
            os.makedirs(packageDir)
        print('  * Processing package: ' + name + '/' + version)
        with open(os.path.join(packageDir, name + '.csproj'), 'a') as pf:

            write_csproj_prefix(pf)
            pf.write('  <ItemGroup>\n')

            dlls = set()
            if 'compile' in data['targets'][target][package]:
                for dll in data['targets'][target][package]['compile']:
                    dlls.add(
                        (name + '/' + version + '/' + dll).lower())
            if 'runtime' in data['targets'][target][package]:
                for dll in data['targets'][target][package]['runtime']:
                    dlls.add((name + '/' + version + '/' + dll).lower())

            for pathInfo in pathInfos:
                for dll in dlls:
                    if pathInfo.lower().endswith(dll):
                        copiedFiles.add(pathInfo)
                        shutil.copy2(pathInfos[pathInfo], packageDir)

            if 'dependencies' in data['targets'][target][package]:
                for dependency in data['targets'][target][package]['dependencies'].keys():
                    depVersion = data['targets'][target][package]['dependencies'][dependency]
                    pf.write('    <ProjectReference Include="../../' +
                             dependency + '/' + depVersion + '/' + dependency + '.csproj" />\n')

            if 'frameworkReferences' in data['targets'][target][package]:
                if not os.path.exists(frameworksDir):
                    os.makedirs(frameworksDir)
                for framework in data['targets'][target][package]['frameworkReferences']:
                    frameworks.add(framework)
                    frameworkDir = os.path.join(
                        frameworksDir, framework)
                    if not os.path.exists(frameworkDir):
                        os.makedirs(frameworkDir)
                    pf.write('    <ProjectReference Include="../../' +
                             frameworksDirName + '/' + framework + '/' + framework + '.csproj" />\n')

            pf.write('    <ProjectReference Include="../../' +
                     frameworksDirName + '/Microsoft.NETCore.App/Microsoft.NETCore.App.csproj" />\n')

            pf.write('  </ItemGroup>\n')
            pf.write('</Project>\n')

# Processing references frameworks
for framework in frameworks:
    with open(os.path.join(frameworksDir, framework, framework + '.csproj'), 'a') as pf:

        write_csproj_prefix(pf)
        pf.write('  <ItemGroup>\n')
        pf.write(
            '    <ProjectReference Include="../Microsoft.NETCore.App/Microsoft.NETCore.App.csproj" />\n')
        pf.write('  </ItemGroup>\n')
        pf.write('</Project>\n')

        for pathInfo in pathInfos:
            if framework.lower() + '.ref' in pathInfo.lower():
                copiedFiles.add(pathInfo)
                shutil.copy2(pathInfos[pathInfo], os.path.join(
                    frameworksDir, framework))

# Processing assemblies in  Microsoft.NETCore.App.Ref
frameworkDir = os.path.join(frameworksDir, 'Microsoft.NETCore.App')
if not os.path.exists(frameworkDir):
    os.makedirs(frameworkDir)
with open(os.path.join(frameworksDir, 'Microsoft.NETCore.App', 'Microsoft.NETCore.App.csproj'), 'a') as pf:
    write_csproj_prefix(pf)
    pf.write('</Project>\n')

    for pathInfo in pathInfos:
        if 'microsoft.netcore.app.ref/' in pathInfo.lower():
            copiedFiles.add(pathInfo)
            shutil.copy2(pathInfos[pathInfo], frameworkDir)

for pathInfo in pathInfos:
    if pathInfo not in copiedFiles:
        print('Not copied to nuget or framework folder: ' + pathInfo)
        othersDir = os.path.join(stubsDir, 'others')
        if not os.path.exists(othersDir):
            os.makedirs(othersDir)
        shutil.copy2(pathInfos[pathInfo], othersDir)

print("\n --> Generated structured stub files: " + stubsDir)

exit(0)
