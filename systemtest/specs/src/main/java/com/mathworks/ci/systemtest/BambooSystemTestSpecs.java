package com.mathworks.ci.systemtest;

import com.atlassian.bamboo.specs.api.builders.AtlassianModule;
import com.atlassian.bamboo.specs.api.builders.plan.Job;
import com.atlassian.bamboo.specs.api.builders.plan.Plan;
import com.atlassian.bamboo.specs.api.builders.plan.Stage;
import com.atlassian.bamboo.specs.api.builders.plan.artifact.Artifact;
import com.atlassian.bamboo.specs.api.builders.project.Project;
import com.atlassian.bamboo.specs.api.builders.task.AnyTask;
import com.atlassian.bamboo.specs.builders.task.ScriptTask;
import com.atlassian.bamboo.specs.util.BambooServer;
import com.atlassian.bamboo.specs.util.SimpleUserPasswordCredentials;
import java.util.LinkedHashMap;
import java.util.Map;

public final class BambooSystemTestSpecs {
    private static final String PROJECT_KEY = "MSYS";
    private static final String PROJECT_NAME = "MATLAB System Tests";
    private static final String PLUGIN_KEY = "com.mathworks.ci.matlab-bamboo-plugin";

    private BambooSystemTestSpecs() {
    }

    public static void main(String[] args) {
        String bambooUrl = env("BAMBOO_URL", "http://localhost:6990/bamboo");
        String username = env("BAMBOO_USERNAME", "admin");
        String password = env("BAMBOO_PASSWORD", "admin");
        String matlabCapability = env("MATLAB_BAMBOO_CAPABILITY", "MATLAB R2026a");

        BambooServer server = new BambooServer(
                bambooUrl,
                new SimpleUserPasswordCredentials(username, password));

        Project project = new Project()
                .key(PROJECT_KEY)
                .name(PROJECT_NAME)
                .description("End-to-end system tests for the MATLAB Bamboo plugin.");

        server.publish(project);
        server.publish(commandPlan(project, matlabCapability));
        server.publish(buildPlan(project, matlabCapability));
        server.publish(testPlan(project, matlabCapability));
    }

    private static Plan commandPlan(Project project, String matlabCapability) {
        return new Plan(project, "MATLAB Command", "CMD")
                .description("Runs the Run MATLAB Command plugin task.")
                .stages(new Stage("Default Stage")
                        .jobs(new Job("MATLAB Command", "JOB1")
                                .tasks(matlabTask("runMATLABCommand", baseConfig(matlabCapability, Map.of(
                                        "matlabCommand", "disp('hello from MATLAB')"))))));
    }

    private static Plan buildPlan(Project project, String matlabCapability) {
        String setup = isWindows() ? """
                @'
                function plan = buildfile
                plan = buildplan(localfunctions);
                end

                function testTask(~)
                disp('Build Successful')
                end
                '@ | Set-Content -Path buildfile.m -Encoding ASCII
                """ : """
                cat > buildfile.m <<'EOF'
                function plan = buildfile
                plan = buildplan(localfunctions);
                end

                function testTask(~)
                disp('Build Successful')
                end
                EOF
                """;

        return new Plan(project, "MATLAB Build", "BLD")
                .description("Runs the Run MATLAB Build plugin task.")
                .stages(new Stage("Default Stage")
                        .jobs(new Job("MATLAB Build", "JOB1")
                                .tasks(
                                        scriptTask("Create MATLAB buildfile", setup),
                                        matlabTask("runMATLABBuild", baseConfig(matlabCapability, Map.of(
                                                "buildTasks", "test",
                                                "buildOptionsChecked", "false",
                                                "buildOptions", ""))))));
    }

    private static Plan testPlan(Project project, String matlabCapability) {
        String setup = isWindows() ? """
                New-Item -ItemType Directory -Force -Path tests | Out-Null
                @'
                classdef ExampleTest < matlab.unittest.TestCase
                    methods (Test)
                        function basicTest(testCase)
                            testCase.verifyTrue(true)
                        end
                    end
                end
                '@ | Set-Content -Path tests/ExampleTest.m -Encoding ASCII
                """ : """
                mkdir -p tests
                cat > tests/ExampleTest.m <<'EOF'
                classdef ExampleTest < matlab.unittest.TestCase
                    methods (Test)
                        function basicTest(testCase)
                            testCase.verifyTrue(true)
                        end
                    end
                end
                EOF
                """;

        return new Plan(project, "MATLAB Tests", "TST")
                .description("Runs the Run MATLAB Tests plugin task.")
                .stages(new Stage("Default Stage")
                        .jobs(new Job("MATLAB Tests", "JOB1")
                                .artifacts(new Artifact("MATLAB Test Artifacts")
                                        .location("matlab-artifacts/test-reports")
                                        .copyPattern("junit.xml")
                                        .shared(true))
                                .tasks(
                                        scriptTask("Create MATLAB test", setup),
                                        matlabTask("runMATLABTest", baseConfig(matlabCapability, Map.ofEntries(
                                                Map.entry("srcFolderChecked", "false"),
                                                Map.entry("srcfolder", ""),
                                                Map.entry("byFolderChecked", "true"),
                                                Map.entry("testFolders", "tests"),
                                                Map.entry("byTagChecked", "false"),
                                                Map.entry("testTag", ""),
                                                Map.entry("pdfChecked", "false"),
                                                Map.entry("pdf", "matlab-artifacts/test-reports/report.pdf"),
                                                Map.entry("stmChecked", "false"),
                                                Map.entry("stm", "matlab-artifacts/test-reports/results.mldatx"),
                                                Map.entry("htmlCoverageChecked", "false"),
                                                Map.entry("html", "matlab-artifacts/code-coverage"),
                                                Map.entry("htmlModelCoverageChecked", "false"),
                                                Map.entry("htmlModel", "matlab-artifacts/model-coverage"),
                                                Map.entry("junitChecked", "true"),
                                                Map.entry("junit", "matlab-artifacts/test-reports/junit.xml"),
                                                Map.entry("htmlTestResultsChecked", "false"),
                                                Map.entry("htmlTestResults", "matlab-artifacts/test-reports"),
                                                Map.entry("strictChecked", "false"),
                                                Map.entry("useParallelChecked", "false"),
                                                Map.entry("outputDetail", "Default"),
                                                Map.entry("loggingLevel", "Default")))))));
    }

    private static AnyTask matlabTask(String taskKey, Map<String, String> configuration) {
        return new AnyTask(new AtlassianModule(PLUGIN_KEY + ":" + taskKey))
                .description(taskKey)
                .configuration(configuration);
    }

    private static ScriptTask scriptTask(String description, String body) {
        ScriptTask task = new ScriptTask()
                .description(description)
                .inlineBody(body);
        return isWindows() ? task.interpreterWindowsPowerShell() : task.interpreterBinSh();
    }

    private static Map<String, String> baseConfig(String matlabCapability, Map<String, String> taskConfig) {
        Map<String, String> config = new LinkedHashMap<>();
        config.put("matlabExecutable", matlabCapability);
        config.put("optionsChecked", "false");
        config.put("matlabOptions", "");
        config.putAll(taskConfig);
        return config;
    }

    private static String env(String name, String defaultValue) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private static boolean isWindows() {
        return System.getProperty("os.name").toLowerCase().contains("win");
    }
}
