@echo off
:: ============================================================
:: run_everything.bat
:: ONE double-click runs the ENTIRE research pipeline.
:: Runs all scripts in correct order, saves all results.
::
:: TOTAL EXPECTED TIME: 60-120 minutes
:: DO NOT close this window until it says PIPELINE COMPLETE.
:: ============================================================
title PLEF Complete Research Pipeline
color 0A

cd /d "%~dp0"

echo.
echo  ================================================================
echo   PLEF COMPLETE RESEARCH PIPELINE
echo   Running all steps automatically in correct order.
echo   Expected time: 60 to 120 minutes total.
echo   DO NOT close this window.
echo  ================================================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo  Install Python 3.8.10 from python.org first.
    pause & exit /b 1
)

:: Install colorama silently
python -c "import colorama" >nul 2>&1
if errorlevel 1 (
    echo  Installing colorama...
    python -m pip install --quiet colorama
)

:: Check all required scripts exist
for %%F in (plef_v7.py extended_reddit_download.py multi_dataset_analysis.py experimental_design.py) do (
    if not exist "%%F" (
        echo.
        echo  ERROR: %%F not found in this folder.
        echo  Make sure all scripts are in the same folder.
        pause & exit /b 1
    )
)

echo.
echo  ================================================================
echo   STEP 1 of 4
echo   Downloading more Reddit relationship subreddits
echo   (r/relationships, r/BreakUps, r/survivinginfidelity, etc.)
echo   Expected time: 20-40 minutes
echo  ================================================================
echo.

:: Run extended Reddit download in automatic mode (choice 1 = full download)
echo 1| python extended_reddit_download.py

if errorlevel 1 (
    echo.
    echo  WARNING: Extended Reddit download had errors.
    echo  Continuing with existing data...
)

echo.
echo  ================================================================
echo   STEP 2 of 4
echo   Downloading all research datasets and running full analysis
echo   Datasets: GoEmotions, EmpatheticDialogues, ISEAR,
echo             SemEval 2017, MELD, TweetEval, DailyDialog,
echo             Reddit posts, Consensus
echo   Expected time: 30-60 minutes
echo  ================================================================
echo.

:: Run multi-dataset analysis with A = all datasets
echo A| python multi_dataset_analysis.py

if errorlevel 1 (
    echo.
    echo  WARNING: Multi-dataset analysis had errors on some datasets.
    echo  Continuing with available results...
)

echo.
echo  ================================================================
echo   STEP 3 of 4
echo   Running experimental validation suite
echo   (Hypotheses, Ablation, LEWI, PTI, TEG, Significance tests)
echo   Expected time: 5-10 minutes
echo  ================================================================
echo.

:: Run experimental design with A = all modules
echo A| python experimental_design.py

if errorlevel 1 (
    echo.
    echo  WARNING: Experimental design module had errors.
    echo  Continuing...
)

echo.
echo  ================================================================
echo   STEP 4 of 4
echo   Running auto-analysis on your original Reddit posts
echo   for trajectory metrics (LEWI, NAVA, TEG)
echo  ================================================================
echo.

python auto_analysis.py

echo.
echo  ================================================================
echo   PIPELINE COMPLETE
echo  ================================================================
echo.
echo  Your results are in these folders:
echo.
echo    results\
echo      COMBINED\            ^<-- START HERE
echo        master_report.txt       (summary of all datasets)
echo        cross_dataset_comparison.csv  (open in Excel)
echo        paper_table_all_datasets.txt  (paste into paper)
echo.
echo      goemotions\          (47k Reddit comments, gold labels)
echo      reddit_relationship\ (your posts, trajectory metrics)
echo      empathetic\          (25k emotional dialogues)
echo      isear\               (psychology sentences)
echo      semeval2017\         (Twitter benchmark)
echo      meld\                (TV dialogue)
echo      tweeteval\           (Twitter benchmark 2)
echo      dailydialog\         (human dialogues)
echo      consensus\           (high-confidence silver labels)
echo.
echo      EXPERIMENTAL\        (ablation, hypotheses, LEWI/PTI/TEG)
echo        pre_registered_hypotheses.txt
echo        ablation_study_full.txt
echo        paper_methods_section.tex
echo        paper_ablation_table.txt
echo.
echo  Open results\COMBINED\master_report.txt first.
echo  That is your complete research summary.
echo.
pause
