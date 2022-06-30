import logging
from uuid import uuid4
import traceback
from queue import Queue

import adsk.core, adsk.fusion, adsk.cam

from .fusion_addin_framework import fusion_addin_framework as faf
from .src.ui import InputIds, CommandWindow


# globals ######################################################################
command = None  # needed for custom event handlers see def on_custom_event()
periodic_thread = None  # started in creaed handler and stoppen on destroy
execution_queue = Queue()
i = 0


# handlers #####################################################################
def trigger_command_queue():
    # command cant be retrieved from args --> global instance necessary
    global i

    if command.isValid:
        execution_queue.put(
            lambda: adsk.core.Application.get().activeProduct.rootComponent.bRepBodies.add(
                faf.utils.create_cube((i * 10, 0, 0), 10)
            )
        )
        command.doExecute(False)
        i = i + 1


def on_created(event_args: adsk.core.CommandCreatedEventArgs):
    global command
    command = event_args.command

    adsk.core.Application.get().activeDocument.design.designType = (
        adsk.fusion.DesignTypes.DirectDesignType
    )

    command_window = CommandWindow(command)

    # to get fusion work done from an thread you normally fire a custom event:
    # ao.app.fireCustomEvent(custom_event_id)
    # however since the we are still running a command in the foreground we can not simply execute
    # something fusion related from the custom event handler.
    # Instead we need to call the commad.doExecute(False) method and execute the work tbd from the
    # active commands execute handler.
    # To achieve arbitrary execution we utilize a global execution queue.

    # Note that sometimes it might also work to directly something from the custom event handler
    # or call the command.doExecute(False) method directly from the thread.
    # However the most reliable method is the one described above.

    # thread must be global so it can be killed in the destroy handler
    global periodic_thread

    # in the thread we fire an custom event which fille the execution queue and triggers the command.execute(False) method
    # this can be realized in two method:
    # 1.) The classsic one:
    # 1.1) Create a cusotm event here. If they get created later they wont work. The event handler triggers the command.execute()
    faf.utils.create_custom_event(
        "CommandActionTriggerEventId", lambda event_args: trigger_command_queue()
    )
    # 1.2) fire the custom event from the thread (see thread execute)
    periodic_thread = faf.utils.PeriodicExecuter(
        2,
        lambda: adsk.core.Application.get().fireCustomEvent(
            "CommandActionTriggerEventId"
        ),
    )

    # 2.) Use generic utility for custo events
    # periodic_thread = faf.utils.PeriodicExecuter(
    #     2,
    #     lambda: faf.utils.execute_as_event(
    #         trigger_command_queue, event_id="CommandActionTriggerEventId"
    #     ),
    # )

    periodic_thread.start()

    # if we are in the on created handler we can not use the command.doExecute workaround since
    # the command hasnt been created yet. Also using a custom event as intermediate step wont help.
    # Therefore the initial action must be called directly from here
    adsk.core.Application.get().activeProduct.rootComponent.bRepBodies.add(
        faf.utils.create_cube((0, 0, 10), 10)
    )


def on_input_changed(event_args: adsk.core.InputChangedEventArgs):
    # in the input changed handler we do NOT need to use the custom_event -> execution_queue mechanism.

    global j

    if event_args.input.id == InputIds.Button1.value:
        adsk.core.Application.get().activeProduct.rootComponent.bRepBodies.add(
            faf.utils.create_cube((0, j * 10, 10), 10)
        )
        j = j + 1


def on_preview(event_args: adsk.core.CommandEventArgs):
    # everything in the preview is delted before the next preview objects are build
    # object which were build in the preview handler are also not kept afer the execute handler
    # therfore it makes no sense to use the preview handler in case of an "dynamic" addin
    # instead use the queue/doExecute technique directly from the input changed handler
    pass


def on_execute(event_args: adsk.core.CommandEventArgs):
    # in execute everything works as exspected
    # use adsk.core.Command.doExecute(terminate = False) to remain in the command

    while not execution_queue.empty():
        execution_queue.get()()


def on_destroy(event_args: adsk.core.CommandEventArgs):
    periodic_thread.pause()


### entry point ################################################################
def run(context):
    try:
        ui = adsk.core.Application.get().userInterface

        faf.utils.create_logger(
            faf.__name__,
            [logging.StreamHandler(), faf.utils.TextPaletteLoggingHandler()],
        )

        addin = faf.FusionAddin()
        workspace = faf.Workspace(addin, id="FusionSolidEnvironment")
        tab = faf.Tab(workspace, id="ToolsTab")
        panel = faf.Panel(tab, id="SolidScriptsAddinsPanel")
        control = faf.Control(panel)
        cmd = faf.AddinCommand(
            control,
            resourceFolder="lightbulb",
            name="GenericDynamicAddin",
            commandCreated=on_created,
            # inputChanged=on_input_changed,
            executePreview=on_preview,
            execute=on_execute,
            destroy=on_destroy,
        )

    except:
        msg = "Failed:\n{}".format(traceback.format_exc())
        if ui:
            ui.messageBox(msg)
        print(msg)


def stop(context):
    try:
        ui = adsk.core.Application.get().userInterface
        faf.stop()
    except:
        msg = "Failed:\n{}".format(traceback.format_exc())
        if ui:
            ui.messageBox(msg)
        print(msg)
